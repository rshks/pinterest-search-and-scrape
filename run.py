#!/usr/bin/env python3
import os
import sys
import re
import subprocess
import shutil
import threading
import queue
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
import requests
import shlex

# Import functions directly from the scraper module
from pinterest_browser_scraper import setup_browser, extract_image_urls_method1, extract_image_urls_method2

def clean_folder_name(name):
    """Create a safe folder name from a search term"""
    # Replace characters not allowed in folder names
    safe_name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace spaces with underscores
    safe_name = safe_name.replace(' ', '_')
    # Trim if too long
    if len(safe_name) > 100:
        safe_name = safe_name[:100]
    return safe_name

def parse_search_terms_file(file_path):
    """Parse the search_terms.txt file and return a list of tuples (search_term, image_count)"""
    search_terms = []
    default_count = 100  # Default image count if not specified
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # Skip empty lines and comments
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            # Check for default image count setting
            if line.startswith('DEFAULT_IMAGES:'):
                try:
                    default_count = int(line.split(':', 1)[1].strip())
                    print(f"Using default image count: {default_count}")
                except ValueError:
                    print(f"Warning: Invalid DEFAULT_IMAGES format, using default count (100)")
                continue
                
            # Skip completed lines
            if line.startswith('DONE - '):
                print(f"Skipping completed search: {line[7:].strip()}")
                continue
                
            # Extract search term and count
            count = default_count
            term = line
            
            # Look for quoted search term
            match = re.search(r'"([^"]+)"', line)
            if match:
                term = match.group(1)  # Get exactly what's between quotes
                
                # Check for count after the quote
                after_quote = line[line.rfind('"')+1:]
                if ':' in after_quote:
                    try:
                        count = int(after_quote.split(':', 1)[1].strip())
                    except ValueError:
                        print(f"Warning: Invalid image count format for '{line}', using default count ({default_count})")
            
            search_terms.append((term, count))
            print(f"Added search term: '{term}' with count {count}")
                
    return search_terms

def calculate_scrolls_needed(image_count):
    """Calculate the number of scrolls needed based on the requested image count.
    Pinterest typically loads about 10-20 images per scroll, so we add a buffer."""
    # Assuming approximately 15 images per scroll with some buffer
    return max(15, int(image_count / 10) + 10)  # Minimum 15 scrolls, or estimated + buffer

def main():
    """Main function to run the Pinterest image downloader."""
    print("\n===== Pinterest Image Downloader =====\n")
    
    # Parse search terms from the file
    search_terms = parse_search_terms_file("search_terms.txt")
    
    if not search_terms:
        print("No search terms found in search_terms.txt. Please add some search terms.")
        return
    
    print(f"Found {len(search_terms)} search terms to process:")
    for i, (term, count) in enumerate(search_terms, 1):
        # Use the actual term - no special "short name" processing
        print(f"  {i}. {term} ({count} images)")
    print("\n")
    
    # Create the output directory if it doesn't exist
    output_dir = "pinterest_images"
    os.makedirs(output_dir, exist_ok=True)
    
    # Process each search term
    successful_terms = 0
    results = []
    
    for term, count in search_terms:
        try:
            # Create a filesystem-safe folder name from the search term
            folder_name = clean_folder_name(term)
            
            # Create the folder for this search term
            folder_path = os.path.join(output_dir, folder_name)
            
            print(f"\n===> Processing: {term} ({count} images) <===\n")
            print(f"- Creating folder: {folder_name}")
            os.makedirs(folder_path, exist_ok=True)
            
            # Extract URLs and download images in a single process
            url_queue = scroll_and_extract_urls(term, max_images=count, max_scrolls=30)
            
            # Download images from the extracted URLs
            downloaded = download_images(url_queue, folder_path, max_images=count)
            
            print(f"✓ Successfully processed '{term}'")
            print(f"  Downloaded {downloaded} images to folder: {folder_name}\n")
            
            successful_terms += 1
            results.append((True, term, downloaded, count, folder_name))
        except Exception as e:
            print(f"❌ Error processing '{term}': {str(e)}")
            results.append((False, term, 0, count, ""))
    
    # Print summary
    print("\n===== Download Summary =====\n")
    print(f"Successfully processed {successful_terms} out of {len(search_terms)} search terms")
    
    for success, term, downloaded, requested, folder in results:
        if success:
            print(f"✓ Success: {term} ({downloaded}/{requested} images) -> {folder}")
        else:
            print(f"❌ Failed: {term} (0/{requested} images)")
    
    # Open the output directory
    print("\nOpening the pinterest_images folder...")
    try:
        os.startfile(output_dir)
    except:
        pass  # Ignore if we can't open the folder
    
    print("\nDone! All your images have been downloaded to their respective folders.")

def process_search_term_parallel(search_term, image_count, temp_dir, output_dir):
    """
    Process a search term using parallel threads for scrolling and downloading.
    
    Args:
        search_term: The search term to process
        image_count: Number of images to download
        temp_dir: Temporary directory for downloads
        output_dir: Final output directory for images
        
    Returns:
        Tuple of (success, downloaded_count)
    """
    # Create shared state objects for thread communication
    shared_state = {
        'urls_found': 0,          # URLs discovered by scroll thread
        'downloads_completed': 0,  # Downloads completed
        'downloads_failed': 0,     # Downloads that failed
        'scroll_complete': False,  # Indicates scraping is finished
        'success': True,           # Overall success status
    }
    
    # Create lock for thread-safe updates
    state_lock = threading.Lock()
    
    try:
        # Extract URLs directly in the main thread
        url_queue = scroll_and_extract_urls(search_term, image_count, max_scrolls=30)
        
        # Mark scrolling as complete for the download process
        with state_lock:
            shared_state['scroll_complete'] = True
            shared_state['urls_found'] = url_queue.qsize()
        
        # Start the download thread pool
        download_result = download_images_from_queue(
            url_queue, image_count, temp_dir, output_dir, shared_state, state_lock
        )
        
        # Get final download count
        with state_lock:
            downloaded = shared_state['downloads_completed']
            success = shared_state['success'] and download_result
        
        # Move files from temp directory to output directory
        move_files_from_temp(temp_dir, output_dir)
        
        return success, downloaded
    
    except Exception as e:
        print(f"Error processing search term: {str(e)}")
        return False, 0

def scroll_and_extract_urls(search_term, max_images=100, max_scrolls=30):
    """Extract image URLs directly from Pinterest."""
    print(f"- Scraping Pinterest for: '{search_term}'")
    print(f"- Starting search for up to {max_images} images")
    
    url_queue = queue.Queue()
    seen_urls = set()
    total_urls_found = 0
    
    # Set up browser
    print("- Setting up browser")
    browser = setup_browser(headless=False)  # Use visible browser for reliability
    
    try:
        # Use optimized extraction with faster scrolling
        # Increase scrolls since we're waiting less time between them
        adjusted_scrolls = max(max_scrolls, max_images // 5)  # Ensure enough scrolls to find images
        print(f"- Using improved image extraction with {adjusted_scrolls} rapid scrolls")
        
        urls = extract_image_urls_method2(browser, search_term, adjusted_scrolls, max_images)
        
        # Process the URLs
        for url in urls:
            # Skip small thumbnail images
            if "/60x60/" in url:
                continue
                
            # Convert to original URL format if needed
            if "/originals/" not in url:
                url = url.replace("/236x/", "/originals/")
                url = url.replace("/474x/", "/originals/")
                url = url.replace("/736x/", "/originals/")
            
            # Only add new URLs
            if url not in seen_urls and "i.pinimg.com" in url:
                seen_urls.add(url)
                url_queue.put(url)
                total_urls_found += 1
                # Don't print every URL to keep console output cleaner
                if total_urls_found % 10 == 0 or total_urls_found <= 5:
                    print(f"  - Found {total_urls_found} image URLs...")
        
        print(f"- Found {total_urls_found} unique image URLs")
        return url_queue
        
    finally:
        # Always close the browser
        print("- Closing browser")
        browser.quit()

def download_images_from_queue(url_queue, image_count, temp_dir, output_dir, shared_state, lock):
    """Download images from the URL queue until enough images are downloaded."""
    try:
        print(f"- Starting batch download process for up to {image_count} images")
        
        # Create temp directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)
        
        # Get URLs from the queue (up to image_count)
        urls = []
        while not url_queue.empty() and len(urls) < image_count:
            urls.append(url_queue.get())
        
        with lock:
            shared_state['urls_found'] = len(urls)
        
        # Use asyncio to download in batches
        try:
            # Run the async download function
            download_result = asyncio.run(batch_download_to_temp(urls, temp_dir, image_count, shared_state, lock))
            
            # Update state
            with lock:
                success = shared_state['downloads_completed'] > 0
            
            print(f"- Batch download process completed")
            return success
        except Exception as e:
            print(f"- Error in batch download process: {str(e)}")
            with lock:
                shared_state['success'] = False
            return False
        
    except Exception as e:
        print(f"Error in download process: {str(e)}")
        with lock:
            shared_state['success'] = False
        return False

async def batch_download_to_temp(urls, temp_dir, max_images, shared_state, lock):
    """
    Download images in batches to a temporary directory using asyncio.
    Updates shared_state with progress information.
    
    Args:
        urls: List of image URLs to download
        temp_dir: Temporary directory for downloads
        max_images: Maximum number of images to download
        shared_state: Shared state dictionary
        lock: Threading lock for updating shared state
        
    Returns:
        True if successful, False otherwise
    """
    # Limit to max_images
    urls = urls[:max_images]
    batch_size = 10  # Process 10 images at once
    total_batches = (len(urls) + batch_size - 1) // batch_size  # Ceiling division
    
    # Configure timeout and connection limits for aiohttp
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    
    print(f"- Starting batch downloads with {total_batches} batches of up to {batch_size} images each")
    
    async with aiohttp.ClientSession(
        timeout=timeout, 
        connector=connector,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.pinterest.com/'
        }
    ) as session:
        # Process in batches
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(urls))
            batch_urls = urls[start_idx:end_idx]
            
            print(f"  - Processing batch {batch_num + 1}/{total_batches} ({len(batch_urls)} images)")
            
            # Create download tasks for this batch
            tasks = []
            for i, url in enumerate(batch_urls):
                idx = start_idx + i
                filename = f"image_{idx:04d}.jpg"
                filepath = os.path.join(temp_dir, filename)
                tasks.append(download_single_image_async(session, url, filepath, lock, shared_state))
            
            # Wait for all downloads in this batch to complete
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Show progress
            with lock:
                completed = shared_state['downloads_completed']
                failed = shared_state['downloads_failed']
                print(f"  - Downloaded {completed} images, {failed} failed")
                
                # Check if we've reached the limit
                if completed >= max_images:
                    print(f"  - Reached target of {max_images} images, stopping")
                    break
    
    # Final summary
    with lock:
        completed = shared_state['downloads_completed']
        failed = shared_state['downloads_failed']
        print(f"- Download complete: {completed} successful, {failed} failed")
    
    return True

async def download_single_image_async(session, url, filepath, lock=None, shared_state=None):
    """Download a single image asynchronously using aiohttp."""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                # Read image data
                image_data = await response.read()
                
                # Save to file using asyncio.to_thread for non-blocking file operations
                # Instead of trying to use asyncio.to_thread as a context manager, call it directly
                f = await asyncio.to_thread(open, filepath, 'wb')
                await asyncio.to_thread(f.write, image_data)
                await asyncio.to_thread(f.close)  # Make sure to close the file
                
                # Update shared state if provided
                if lock and shared_state:
                    with lock:
                        shared_state['downloads_completed'] += 1
                
                return True
            else:
                # Update shared state if provided
                if lock and shared_state:
                    with lock:
                        shared_state['downloads_failed'] += 1
                
                return False
    except Exception as e:
        # Update shared state if provided
        if lock and shared_state:
            with lock:
                shared_state['downloads_failed'] += 1
                print(f"  - Failed to download {url}: {str(e)}")
        
        # Return the exception to be handled by the caller
        return e

def move_files_from_temp(temp_dir, output_dir):
    """Move downloaded files from temp directory to output directory."""
    try:
        # Check if temp directory exists and has contents
        if not os.path.exists(temp_dir):
            return
            
        # First check for nested folders in temp_dir
        nested_folders = [f for f in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, f))]
        
        if nested_folders:
            # Handle nested folder case
            for folder in nested_folders:
                nested_folder = os.path.join(temp_dir, folder)
                for file in os.listdir(nested_folder):
                    if file.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                        src = os.path.join(nested_folder, file)
                        dst = os.path.join(output_dir, file)
                        shutil.move(src, dst)
        else:
            # Move files directly from temp_dir
            for file in os.listdir(temp_dir):
                if file.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    src = os.path.join(temp_dir, file)
                    dst = os.path.join(output_dir, file)
                    shutil.move(src, dst)
    
    except Exception as e:
        print(f"Error moving files: {str(e)}")

def download_images(url_queue, output_dir, max_images=100):
    """Download images from the URL queue using batch processing with asyncio."""
    print("- Download process started")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get all URLs from the queue
    urls = []
    while not url_queue.empty() and len(urls) < max_images:
        urls.append(url_queue.get())
    
    total_urls = len(urls)
    print(f"- Preparing to download {total_urls} images in batches")
    
    if not urls:
        print("- No URLs to download")
        return 0
    
    # Use asyncio to download in batches
    try:
        # Run the async download function
        downloaded = asyncio.run(batch_download_images(urls, output_dir, max_images))
        print(f"- Successfully downloaded {downloaded} images")
        return downloaded
    except Exception as e:
        print(f"- Error in batch download process: {str(e)}")
        return 0

async def batch_download_images(urls, output_dir, max_images):
    """
    Download images in batches using asyncio for improved performance.
    
    Args:
        urls: List of image URLs to download
        output_dir: Directory to save images
        max_images: Maximum number of images to download
        
    Returns:
        Number of successfully downloaded images
    """
    # Limit to max_images
    urls = urls[:max_images]
    batch_size = 10  # Process 10 images at once
    total_batches = (len(urls) + batch_size - 1) // batch_size  # Ceiling division
    
    # Set up shared counter and completed images list
    download_counter = 0
    failed_downloads = []
    
    # Configure timeout and connection limits for aiohttp
    timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
    connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
    
    print(f"- Starting batch downloads with {total_batches} batches of up to {batch_size} images each")
    
    async with aiohttp.ClientSession(
        timeout=timeout, 
        connector=connector,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.pinterest.com/'
        }
    ) as session:
        # Process in batches
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(urls))
            batch_urls = urls[start_idx:end_idx]
            
            print(f"  - Processing batch {batch_num + 1}/{total_batches} ({len(batch_urls)} images)")
            
            # Create download tasks for this batch
            tasks = []
            for i, url in enumerate(batch_urls):
                idx = start_idx + i
                filename = f"image_{idx:04d}.jpg"
                filepath = os.path.join(output_dir, filename)
                tasks.append(download_single_image_async(session, url, filepath))
            
            # Wait for all downloads in this batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_downloads.append(batch_urls[i])
                    print(f"  - Failed to download {batch_urls[i]}: {str(result)}")
                elif result:
                    download_counter += 1
            
            # Show progress
            print(f"  - Downloaded {download_counter} images so far")
    
    # Final summary
    print(f"- Download complete: {download_counter} successful, {len(failed_downloads)} failed")
    return download_counter

if __name__ == "__main__":
    main()
