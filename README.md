# Pinterest Image Scraper

A tool for automatically downloading images from Pinterest based on search terms.

## Installation

1. Make sure you have Python 3.6 or higher installed on your system.
2. Run the installation script to install all required dependencies:

```
python install.py
```

## Mac Installation (For Non-Technical Users)

If you're using a Mac and aren't familiar with coding, follow these step-by-step instructions:

1. **Install Python** (if you don't already have it):
   - Go to https://www.python.org/downloads/
   - Download the latest version for macOS
   - Open the downloaded file and follow the installation wizard
   - When the installation is complete, restart your computer

2. **Download this project**:
   - Download this project as a ZIP file and unzip it to a folder
   - Remember where you saved it (for example, in your Downloads folder)

3. **Open Terminal**:
   - Press Command+Space to open Spotlight Search
   - Type "Terminal" and press Enter
   - This opens a command-line window

4. **Navigate to the project folder**:
   - Type `cd ` (with a space after cd)
   - Drag and drop the folder where you unzipped the project into the Terminal window
   - Press Enter

5. **Make the installation script executable**:
   - Type this command exactly as shown and press Enter:
     ```
     chmod +x install.sh
     ```

6. **Run the installation script**:
   - Type this command and press Enter:
     ```
     ./install.sh
     ```
   - Wait for the installation to complete (this might take a few minutes)
   - Press Enter when prompted to exit the installer

7. **Edit search terms**:
   - Find the file named `search_terms.txt` in the project folder
   - Right-click and open it with TextEdit or any text editor
   - Add your Pinterest search terms (see Example section below)
   - Save and close the file

8. **Run the scraper**:
   - Return to the Terminal window (which should still be open)
   - Type this command and press Enter:
     ```
     python3 run.py
     ```
   - The program will start downloading images based on your search terms
   - When it's finished, it will automatically open the folder with your downloaded images

9. **Finding your downloaded images**:
   - All images are saved in the `pinterest_images` folder inside the project folder
   - Each search term has its own subfolder

## Usage

1. Edit the `search_terms.txt` file to add your Pinterest search terms:
   - Each line should contain a search term in quotes, optionally followed by a colon and the number of images to download
   - Example: `"mountain landscape":50` will download 50 images of mountain landscapes
   - You can set a default image count for all searches with `DEFAULT_IMAGES:200`
   - Lines starting with `#` are treated as comments

2. Run the scraper:

```
python run.py
```

3. The scraper will:
   - Process each search term in the file
   - Create folders for each search term in the `pinterest_images` directory
   - Download the requested number of images for each search term
   - Open the folder with the downloaded images when complete

## Example search_terms.txt file

```
# Pinterest Search Terms
# Set default image count
DEFAULT_IMAGES:200

# Fashion search terms
"Y2K glamour (ed hardy, 2000s dolce&gabbana, 2000s Dior)"
"Gorpcore (gorpcore aesthetics, technical outfit)":150
"Douyin (douyin aesthetics, Harajuku aesthetics)"

# Lines starting with DONE are skipped
DONE - "already processed search"
```

## Notes

- The scraper uses a Chrome browser through Selenium, which will be automatically downloaded
- Search terms that have been processed will be marked with "DONE - " in the search_terms.txt file
- All images are downloaded to the `pinterest_images` directory, with a subfolder for each search term 