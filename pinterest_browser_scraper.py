import os
import time
import json
import argparse
import logging
import traceback
import requests
from urllib.parse import quote, quote_plus
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, SessionNotCreatedException
from concurrent.futures import ThreadPoolExecutor
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pinterest_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def setup_browser(headless=True):
    """Set up and return a configured browser instance"""
    logger.info("Setting up Chrome browser")
    options = Options()
    if headless:
        logger.info("Running in headless mode")
        options.add_argument("--headless=new")  # Updated headless mode syntax
    
    # Common options to improve stability
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    
    # Set user agent to appear as a regular browser
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
    options.add_argument(f"--user-agent={user_agent}")
    
    try:
        # Use webdriver_manager to automatically download the correct ChromeDriver version
        logger.info("Attempting to get compatible ChromeDriver")
        service = Service(ChromeDriverManager().install())
        browser = webdriver.Chrome(service=service, options=options)
        logger.info("Chrome browser initialized successfully")
        return browser
    except SessionNotCreatedException as e:
        logger.error(f"Chrome version mismatch: {str(e)}")
        logger.info("Trying alternative ChromeDriver setup...")
        # If automatic version fails, try with default service
        try:
            browser = webdriver.Chrome(options=options)
            logger.info("Chrome browser initialized with default service")
            return browser
        except Exception as e2:
            logger.error(f"Failed to initialize Chrome with default service: {str(e2)}")
            raise
    except Exception as e:
        logger.error(f"Failed to initialize Chrome browser: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def extract_image_urls_method1(browser, search_term, num_scrolls=10):
    """
    Extract image URLs using method 1: Direct DOM extraction
    This method extracts image URLs directly from the DOM
    """
    from urllib.parse import quote_plus
    # Properly encode the search term - use the exact term as provided
    search_url = f"https://www.pinterest.com/search/pins/?q={quote_plus(search_term)}&rs=typed"
    logger.info(f"Navigating to search URL: {search_url}")
    
    try:
        browser.get(search_url)
        logger.info(f"Loaded search page for '{search_term}'")
        
        # Wait for page to load
        logger.info("Waiting for images to load")
        try:
            WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            logger.info("Images loaded successfully")
        except TimeoutException:
            logger.warning("Timeout waiting for images to load, continuing anyway")
        
        # Scroll down to load more images
        logger.info(f"Scrolling to load more images ({num_scrolls} scrolls)")
        for i in range(num_scrolls):
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # Wait for new content to load
            time.sleep(2)
            logger.info(f"Scroll {i+1}/{num_scrolls} completed")
        
        # Execute JavaScript to extract image URLs
        logger.info("Extracting image URLs from the page")
        script = """
        return Array.from(document.querySelectorAll('img'))
            .map(x => x.src)
            .filter(x => x.indexOf('236x') !== -1)
            .map(x => x.replace('236x', 'originals'));
        """
        image_urls = browser.execute_script(script)
        logger.info(f"Found {len(image_urls)} image URLs using method 1")
        
        # Log a few URLs for debugging
        if image_urls:
            logger.info(f"Sample URLs: {image_urls[:3]}")
        else:
            logger.warning("No image URLs found with method 1")
            
            # Try an alternative selector
            logger.info("Trying alternative image selector")
            alt_script = """
            return Array.from(document.querySelectorAll('[data-test-id="pinrep-image"] img, [data-test-id="pin"] img'))
                .map(x => x.src)
                .filter(x => x && x.length > 0);
            """
            alt_urls = browser.execute_script(alt_script)
            logger.info(f"Alternative selector found {len(alt_urls)} URLs")
            if alt_urls:
                logger.info(f"Sample alternative URLs: {alt_urls[:3]}")
                image_urls = alt_urls
        
        return image_urls
    except Exception as e:
        logger.error(f"Error in extract_image_urls_method1: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def extract_image_urls_method2(browser, search_term, num_scrolls=10):
    """
    Extract image URLs using method 2: Pin elements
    This method extracts images from pin elements
    """
    from urllib.parse import quote_plus
    # Properly encode the search term - use the exact term as provided
    search_url = f"https://www.pinterest.com/search/pins/?q={quote_plus(search_term)}&rs=typed"
    logger.info(f"Navigating to search URL for method 2: {search_url}")
    
    try:
        browser.get(search_url)
        logger.info(f"Loaded search page for method 2: '{search_term}'")
        
        # Wait for page to load
        logger.info("Waiting for images to load")
        try:
            WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            logger.info("Images loaded successfully")
        except TimeoutException:
            logger.warning("Timeout waiting for images to load, continuing anyway")
        
        # Scroll down to load more images
        logger.info(f"Scrolling to load more images for method 2 ({num_scrolls} scrolls)")
        for i in range(num_scrolls):
            browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            # Wait longer between scrolls for method 2
            time.sleep(2.5)
            logger.info(f"Method 2 scroll {i+1}/{num_scrolls} completed")
        
        # Try to get the resource URLs
        image_urls = []
        try:
            # Look for pin elements with image data
            logger.info("Attempting to extract image URLs from pin elements")
            script = """
            // This method attempts to find pins with images
            var imageUrls = [];
            try {
                // Try multiple selectors to find pins
                var pins = Array.from(document.querySelectorAll('[data-test-pin-id], [data-test-id="pin"], .Pin'));
                console.log("Found " + pins.length + " pin elements");
                
                pins.forEach(function(pin) {
                    var img = pin.querySelector('img');
                    if (img && img.src) {
                        var src = img.src;
                        // Look for various image patterns
                        if (src.indexOf('236x') !== -1) {
                            imageUrls.push(src.replace('236x', 'originals'));
                        } else if (src.indexOf('474x') !== -1) {
                            imageUrls.push(src.replace('474x', 'originals'));
                        } else if (src.indexOf('736x') !== -1) {
                            imageUrls.push(src.replace('736x', 'originals'));
                        } else if (src.length > 20 && !src.includes('data:image')) {
                            // Include any non-data URLs that look like images
                            imageUrls.push(src);
                        }
                    }
                });
                
                // If we didn't find many, try a broader selector
                if (imageUrls.length < 10) {
                    var allImages = Array.from(document.querySelectorAll('img[srcset]'));
                    allImages.forEach(function(img) {
                        if (img.srcset) {
                            // Get the highest resolution from srcset
                            var srcset = img.srcset.split(',');
                            var lastSrc = srcset[srcset.length - 1].trim().split(' ')[0];
                            if (lastSrc && lastSrc.length > 20) {
                                imageUrls.push(lastSrc);
                            }
                        }
                    });
                }
            } catch (e) {
                console.error("Error in JavaScript extraction:", e);
            }
            return imageUrls;
            """
            image_urls = browser.execute_script(script)
            logger.info(f"Found {len(image_urls)} image URLs using method 2")
            
            # Log a few URLs for debugging
            if image_urls:
                logger.info(f"Method 2 sample URLs: {image_urls[:3]}")
            else:
                logger.warning("No image URLs found with method 2")
        except Exception as e:
            logger.error(f"Error extracting image URLs in method 2: {str(e)}")
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(f"Error in extract_image_urls_method2: {str(e)}")
        logger.error(traceback.format_exc())
    
    return image_urls

def download_image(args):
    """Download a single image"""
    url, folder, index = args
    try:
        # Create a unique filename
        file_ext = url.split('.')[-1].split('?')[0]  # Get extension without query params
        if len(file_ext) > 5 or not file_ext:  # If extension seems invalid
            file_ext = 'jpg'
        
        filename = f"image_{index:04d}.{file_ext}"
        filepath = os.path.join(folder, filename)
        
        # Download the image
        logger.debug(f"Downloading image from {url}")
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            logger.debug(f"Successfully downloaded {url} to {filepath}")
            return True, url
        else:
            logger.warning(f"Failed to download {url}: HTTP {response.status_code}")
            return False, url
    except Exception as e:
        logger.warning(f"Error downloading {url}: {str(e)}")
        return False, url

def download_images(image_urls, output_folder, max_images=50, workers=5):
    """Download images in parallel"""
    if not image_urls:
        logger.warning("No image URLs to download")
        return 0
    
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    logger.info(f"Created output folder: {output_folder}")
    
    # Limit to max_images
    urls_to_download = image_urls[:max_images]
    logger.info(f"Downloading {len(urls_to_download)} images to {output_folder}")
    
    # Prepare download tasks
    tasks = [(url, output_folder, idx) for idx, url in enumerate(urls_to_download)]
    
    # Download images in parallel
    success_count = 0
    failed_urls = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(download_image, tasks))
        for success, url in results:
            if success:
                success_count += 1
            else:
                failed_urls.append(url)
    
    logger.info(f"Successfully downloaded {success_count} images")
    if failed_urls:
        logger.warning(f"Failed to download {len(failed_urls)} images")
        logger.debug(f"Failed URLs: {failed_urls[:5]}")
    
    return success_count

def pinterest_search_scraper(search_term, output_folder=None, max_images=50, num_scrolls=10, workers=5, headless=True):
    """Main function to scrape Pinterest search results"""
    # Set up output folder
    if output_folder is None:
        output_folder = search_term.replace(" ", "_")
    
    logger.info(f"Scraping Pinterest for search term: '{search_term}'")
    logger.info(f"Will download up to {max_images} images to '{output_folder}'")
    
    # Setup browser
    browser = None
    try:
        browser = setup_browser(headless)
        
        # Try first method
        logger.info("Trying extraction method 1")
        image_urls = extract_image_urls_method1(browser, search_term, num_scrolls)
        
        # If first method didn't find enough images, try second method
        if len(image_urls) < max_images:
            logger.info(f"Method 1 found only {len(image_urls)} images, trying method 2")
            browser.refresh()  # Refresh page before trying again
            time.sleep(3)
            additional_urls = extract_image_urls_method2(browser, search_term, num_scrolls)
            
            # Combine URLs from both methods, removing duplicates
            all_urls = list(set(image_urls + additional_urls))
            logger.info(f"Combined methods found {len(all_urls)} unique image URLs")
            image_urls = all_urls
        
        # Download images
        downloaded_count = download_images(image_urls, output_folder, max_images, workers)
        
        return {
            "success": downloaded_count > 0,
            "search_term": search_term,
            "images_found": len(image_urls),
            "images_downloaded": downloaded_count,
            "output_folder": output_folder
        }
    
    except Exception as e:
        logger.error(f"Error scraping Pinterest: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "search_term": search_term,
            "error": str(e)
        }
    finally:
        if browser:
            logger.info("Closing browser")
            try:
                browser.quit()
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Download Pinterest search result images')
    parser.add_argument('search_terms', nargs='+', help='Search terms to look for on Pinterest')
    parser.add_argument('-n', '--num-images', type=int, default=50,
                        help='Maximum number of images to download')
    parser.add_argument('-o', '--output-dir', type=str, default='pinterest_images',
                        help='Directory to save the images in')
    parser.add_argument('-s', '--scrolls', type=int, default=10,
                        help='Number of times to scroll down the page')
    parser.add_argument('-w', '--workers', type=int, default=5,
                        help='Number of download workers to use')
    parser.add_argument('--no-headless', action='store_true',
                        help='Run Chrome in non-headless mode (you can see the browser)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--extraction-only', action='store_true',
                        help='Only extract image URLs without downloading them')
    
    args = parser.parse_args()
    
    # Set logging level based on verbose flag
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    logger.info(f"Starting Pinterest scraper with search terms: {args.search_terms}")
    
    for term in args.search_terms:
        term_folder = os.path.join(args.output_dir, term.replace(" ", "_").replace("(", "").replace(")", "").replace(",", ""))
        
        logger.info(f"Processing search term: '{term}'")
        if args.extraction_only:
            # In extraction-only mode, we just extract URLs and print them
            extract_pinterest_image_urls(term, args.scrolls, args.no_headless)
        else:
            # Normal mode - extract and download images
            result = pinterest_search_scraper(
                term,
                output_folder=term_folder,
                max_images=args.num_images,
                num_scrolls=args.scrolls,
                workers=args.workers,
                headless=not args.no_headless
            )
            
            if result["success"]:
                logger.info(f"Successfully downloaded {result['images_downloaded']} images for '{term}'")
            else:
                logger.error(f"Failed to download images for '{term}'")
                if "error" in result:
                    logger.error(f"Error: {result['error']}")
    
    logger.info("All search terms processed")

def extract_pinterest_image_urls(search_term, scrolls, no_headless):
    """Extract and print image URLs without downloading them."""
    logger.info(f"Scraping Pinterest for search term: '{search_term}'")
    
    # Set up the Chrome browser
    logger.info("Setting up Chrome browser")
    options = webdriver.ChromeOptions()
    
    if not no_headless:
        logger.info("Running in headless mode")
        options.add_argument("--headless=new")
    
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    
    logger.info("Attempting to get compatible ChromeDriver")
    # Match the same service class used elsewhere in the code
    try:
        from selenium.webdriver.chrome.service import Service as ChromeService
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
    except ImportError:
        # Fall back to Service if ChromeService is not available
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    logger.info("Chrome browser initialized successfully")
    
    # Navigate to Pinterest search
    try:
        # Try extraction method 1
        logger.info("Trying extraction method 1")
        # Properly URL encode the search term - use the exact term as provided
        encoded_search_term = quote_plus(search_term)
        search_url = f"https://www.pinterest.com/search/pins/?q={encoded_search_term}&rs=typed"
        logger.info(f"Navigating to search URL: {search_url}")
        driver.get(search_url)
        
        # Wait for the page to load
        logger.info(f"Loaded search page for '{search_term}'")
        logger.info("Waiting for images to load")
        time.sleep(2)  # Initial wait for images to load
        
        # Check if images loaded successfully
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "img"))
            )
            logger.info("Images loaded successfully")
        except:
            logger.warning("Timed out waiting for images to load")
        
        # Scroll down to load more images
        logger.info(f"Scrolling to load more images ({scrolls} scrolls)")
        
        # Print a clear marker for the start of URL extraction
        print("\n==== PINTEREST URL EXTRACTION STARTING ====\n")
        
        for i in range(scrolls):
            # Scroll down
            driver.execute_script("window.scrollBy(0, 1000);")
            # Wait for new images to load
            time.sleep(2)
            logger.info(f"Scroll {i+1}/{scrolls} completed")
            
            # After each scroll, extract and print URLs
            print(f"\n--- EXTRACTING URLS FROM SCROLL {i+1} ---\n")
            
            # Method 1: Extract from src attributes
            image_elements = driver.find_elements(By.TAG_NAME, "img")
            for img in image_elements:
                src = img.get_attribute("src")
                if src and "i.pinimg.com" in src:
                    # Convert to originals URL if needed
                    if '/originals/' not in src:
                        src = src.replace('/236x/', '/originals/')
                        src = src.replace('/474x/', '/originals/')
                        src = src.replace('/736x/', '/originals/')
                    
                    # Print in the format expected by our parallel code
                    print(f"IMAGE_URL: {src}")
            
            # Method 2: Extract from srcset attributes
            for img in image_elements:
                srcset = img.get_attribute("srcset")
                if srcset:
                    # Get the highest resolution from srcset
                    parts = srcset.split(',')
                    for part in parts:
                        if part.strip() and len(part.strip()) > 10:
                            url = part.strip().split(' ')[0]
                            if "i.pinimg.com" in url:
                                # Convert to originals URL if needed
                                if '/originals/' not in url:
                                    url = url.replace('/236x/', '/originals/')
                                    url = url.replace('/474x/', '/originals/')
                                    url = url.replace('/736x/', '/originals/')
                                
                                # Print in the format expected by our parallel code
                                print(f"IMAGE_URL: {url}")
            
            # Method 3: Try to extract from JavaScript
            try:
                script = """
                return Array.from(document.querySelectorAll('img'))
                    .map(x => x.src)
                    .filter(x => x && x.includes('i.pinimg.com'));
                """
                js_urls = driver.execute_script(script)
                for url in js_urls:
                    if url and "i.pinimg.com" in url:
                        # Convert to originals URL if needed
                        if '/originals/' not in url:
                            url = url.replace('/236x/', '/originals/')
                            url = url.replace('/474x/', '/originals/')
                            url = url.replace('/736x/', '/originals/')
                        
                        # Print in the format expected by our parallel code
                        print(f"IMAGE_URL: {url}")
            except Exception as e:
                logger.error(f"Error extracting URLs with JavaScript: {e}")
        
        # Extract image URLs at the end as well to catch any that weren't printed during scrolls
        logger.info("Extracting image URLs from the page")
        
        # Method 4: Try to extract from pin elements
        try:
            script = """
            var urls = [];
            try {
                // Try to find pins with images
                var pins = Array.from(document.querySelectorAll('[data-test-pin-id], [data-test-id="pin"], .Pin'));
                console.log("Found " + pins.length + " pin elements");
                
                pins.forEach(function(pin) {
                    var img = pin.querySelector('img');
                    if (img && img.src) {
                        urls.push(img.src);
                    }
                });
            } catch (e) {
                console.error("Error in pin extraction:", e);
            }
            return urls;
            """
            pin_urls = driver.execute_script(script)
            for url in pin_urls:
                if url and "i.pinimg.com" in url:
                    # Convert to originals URL if needed
                    if '/originals/' not in url:
                        url = url.replace('/236x/', '/originals/')
                        url = url.replace('/474x/', '/originals/')
                        url = url.replace('/736x/', '/originals/')
                    
                    # Print in the format expected by our parallel code
                    print(f"IMAGE_URL: {url}")
        except Exception as e:
            logger.error(f"Error extracting URLs from pins: {e}")
        
        # Print a clear marker for the end of URL extraction
        print("\n==== PINTEREST URL EXTRACTION COMPLETED ====\n")
                
    except Exception as e:
        logger.error(f"Error extracting URLs for '{search_term}': {e}")
        import traceback
        logger.debug(traceback.format_exc())
    finally:
        # Close the browser
        logger.info("Closing browser")
        driver.quit()

if __name__ == "__main__":
    main() 