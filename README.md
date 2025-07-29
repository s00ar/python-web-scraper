# Automated Multi-Search Scraper

This project automates Google searches to extract emails and phone numbers using Selenium with Undetected ChromeDriver.  
It supports multiple queries, skips incomplete results if desired, and saves data to CSV/Excel with unique filenames.  
Ideal for lead generation, research, and market analysis.

## Features
- Undetected ChromeDriver integration to avoid detection
- Multiple consecutive searches with minimal manual input
- Email and phone extraction using regex
- Option to skip incomplete results (missing phone or email)
- Saves data to CSV and Excel with unique filenames
- Flexible category and country targeting

## Requirements
- Python 3.8+
- Google Chrome installed

## Installation
```bash
pip install undetected-chromedriver selenium pandas
```

## Usage
Run the script:
```bash
python main.py
```
Follow the prompts to enter:
- Category (e.g., distribuidoras)
- Country code (e.g., PE)
- Include incomplete results (yes/no)
- Number of pages to scrape

Data will be saved in the `output/` folder.

## Gitignore
Generated files like CSV/Excel, virtual environment folders, and cache files are excluded via `.gitignore`.

## License
MIT License
