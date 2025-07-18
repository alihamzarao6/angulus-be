from agents import function_tool
import requests
from typing_extensions import AnyStr, Dict, List, Any
import csv
import os
from datetime import datetime
from typing import List, Dict, Union, Optional
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import zipfile
import json
import logging
from enum import Enum
from db import db
from openai import OpenAI

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tools.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('tools')

# Base URL for serving static files
STATIC_BASE_URL = f"{os.getenv('BASE_URL', 'http://localhost:8000')}/output"

def get_static_url(filename: str) -> str:
    """Convert a file path to a static URL path"""
    return f"{STATIC_BASE_URL}/{filename}"

def extract_visible_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for script_or_style in soup(["script", "style", "meta", "noscript"]):
        script_or_style.decompose()
    return soup.get_text(separator="\n", strip=True)


@function_tool
async def scrape_web_page(url: str) -> str:
    """
    Scrapes the visible text content from a webpage using Playwright.
    Handles JavaScript-rendered content and returns the first 3000 characters.
    
    Args:
        url: The URL of the webpage to scrape
    """
    logger.info(f"Scraping web page: {url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to the URL
            await page.goto(url, wait_until='networkidle')
            
            # Wait for content to be fully loaded
            await page.wait_for_load_state('domcontentloaded')
            
            # Get the page content
            content = await page.content()
            
            # Extract visible text
            visible_text = extract_visible_text(content)
            
            logger.info(f"Successfully scraped {url}")
            await browser.close()
            return visible_text[:3000]
            
        except Exception as e:
            error_msg = f"Error scraping {url}: {str(e)}"
            logger.error(error_msg)
            return f"Error: {str(e)}"
        finally:
            logger.info(f"Completed scraping: {url}")
            await browser.close()


@function_tool
async def create_csv_file(url: str, context: str) -> Optional[str]:
    """
    Extracts structured data from a webpage using OpenAI and saves it as a CSV file.
    Uses a staged approach to analyze content and determine the optimal CSV structure.
    
    Args:
        url: The URL of the webpage to extract data from
        context: Additional context or instructions about what kind of data to extract
    """
    logger.info(f"[STAGE 0] Starting CSV extraction process for URL: {url}")
    if context:
        logger.info(f"[STAGE 0] Extraction context provided: {context}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Stage 1: Get page content
            logger.info("[STAGE 1] Loading page content...")
            await page.goto(url, wait_until='networkidle')
            await page.wait_for_load_state('domcontentloaded')
            content = await page.content()
            visible_text = extract_visible_text(content)
            logger.info(f"[STAGE 1] Successfully extracted {len(visible_text)} characters of visible text")
            
            # Stage 2: Extract maximum tokens without hitting context limit
            logger.info("[STAGE 2] Processing content for token limits...")
            max_tokens = 12000
            original_length = len(visible_text)
            visible_text = visible_text[:max_tokens * 4]  # Rough estimate: 4 chars per token
            logger.info(f"[STAGE 2] Content length adjusted from {original_length} to {len(visible_text)} characters")
            
            # Stage 3: Get initial structure and sample rows using OpenAI
            logger.info("[STAGE 3] Analyzing content structure with OpenAI...")
            context_instruction = f"\nAdditional context for extraction: {context}" if context else ""
            structure_prompt = f"""
            Analyze the following webpage content and determine the most appropriate CSV structure.
            {context_instruction}
            
            Return a JSON object with two fields:
            1. row_schema: array of column names that best represent the data
            2. rows: array of objects matching the schema, containing the first few rows of data
            
            Content:
            {visible_text[:4000]}  # First 4000 chars for initial analysis
            
            Return JSON format:
            {{
                "row_schema": ["column1", "column2", ...],
                "rows": [
                    {{"column1": "value1", "column2": "value2", ...}},
                    ...
                ]
            }}
            """
            
            logger.info("[STAGE 3] Sending initial structure analysis request to OpenAI...")
            response = client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": structure_prompt}],
                response_format={"type": "json_object"}
            )
            
            initial_data = json.loads(response.choices[0].message.content)
            row_schema = initial_data["row_schema"]
            all_rows = initial_data["rows"]
            logger.info(f"[STAGE 3] Successfully determined schema: {row_schema}")
            logger.info(f"[STAGE 3] Initial rows extracted: {len(all_rows)}")
            
            # Stage 4: Process remaining content in batches
            logger.info("[STAGE 4] Starting batch processing of remaining content...")
            remaining_text = visible_text[4000:]
            batch_size = 4000  # Process in 4000 char chunks
            total_batches = (len(remaining_text) + batch_size - 1) // batch_size
            logger.info(f"[STAGE 4] Total batches to process: {total_batches}")
            
            for i in range(0, len(remaining_text), batch_size):
                batch_num = (i // batch_size) + 1
                logger.info(f"[STAGE 4] Processing batch {batch_num}/{total_batches}")
                batch = remaining_text[i:i + batch_size]
                
                batch_prompt = f"""
                Extract additional rows of data following this schema: {row_schema}
                from the following content. Return null if no valid rows can be extracted.
                {context_instruction}
                
                Content:
                {batch}
                
                Return JSON format:
                {{
                    "rows": [
                        {{"column1": "value1", "column2": "value2", ...}},
                        ...
                    ]
                }}
                """
                
                logger.info(f"[STAGE 4] Sending batch {batch_num} to OpenAI for processing...")
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[{"role": "user", "content": batch_prompt}],
                    response_format={"type": "json_object"}
                )
                
                batch_data = json.loads(response.choices[0].message.content)
                
                if not batch_data.get("rows"):
                    logger.info(f"[STAGE 4] No valid rows found in batch {batch_num}, stopping batch processing")
                    continue
                    
                new_rows = batch_data["rows"]
                all_rows.extend(new_rows)
                logger.info(f"[STAGE 4] Added {len(new_rows)} rows from batch {batch_num}")
            
            if not all_rows:
                logger.info("[FINAL] No structured data found, returning None")
                return None
                
            # Create output directory if it doesn't exist
            logger.info("[FINAL] Preparing to save CSV file...")
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"structured_data_{timestamp}.csv"
            filepath = os.path.join(output_dir, filename)
            
            # Write to CSV file
            logger.info(f"[FINAL] Writing {len(all_rows)} rows to CSV file...")
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=row_schema)
                writer.writeheader()
                writer.writerows(all_rows)
            
            logger.info(f"[FINAL] Successfully created CSV file at {filepath}")
            await browser.close()
            return get_static_url(filename)
            
        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}"
            logger.error(f"[ERROR] {error_msg}")
            return None
        finally:
            logger.info("[CLEANUP] Closing browser and completing process")
            await browser.close()


@function_tool
async def scrape_multiple_links(url: str, max_links: int = 5, context: str = "") -> str:
    """
    Scrapes content from a parent URL and up to 4 additional links found on the page.
    Uses OpenAI to filter links by relevance to the context and generate summaries of each page's content.
    Stores all content and summaries in a zip file and returns the URL path to the zip file.
    
    Args:
        url: The parent URL to start scraping from
        max_links: Maximum number of links to scrape (including parent)
        context: Additional context to guide link filtering and summarization process
    
    Returns:
        str: URL path to the created zip file containing scraped content and summaries
    """
    logger.info(f"Scraping multiple links starting from: {url} (max_links: {max_links})")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to parent URL
            await page.goto(url)
            
            # Get all links and their text from the page
            links_with_text = await page.eval_on_selector_all('a', '''
                elements => elements.map(el => ({
                    url: el.href,
                    text: el.textContent.trim(),
                    title: el.title || ''
                }))
            ''')
            
            # Filter out non-http links and prepare for relevance check
            valid_links = [
                link for link in links_with_text 
                if link['url'].startswith('http')
            ]
            
            # If we have context, filter links by relevance
            if context and valid_links:
                logger.info("Filtering links by relevance to context...")
                
                # Prepare link information for relevance check
                link_info = "\n".join([
                    f"URL: {link['url']}\nText: {link['text']}\nTitle: {link['title']}\n"
                    for link in valid_links
                ])
                
                relevance_prompt = f"""
                Given the following context and list of links, identify the most relevant links.
                Context: {context}
                
                Links to evaluate:
                {link_info}
                
                Return a JSON array of URLs that are most relevant to the context, ordered by relevance.
                Maximum number of links to return: {max_links-1}
                
                Format:
                {{
                    "relevant_urls": ["url1", "url2", ...]
                }}
                """
                
                response = client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[{"role": "user", "content": relevance_prompt}],
                    response_format={"type": "json_object"}
                )
                
                relevant_urls = json.loads(response.choices[0].message.content)["relevant_urls"]
                
                # Filter valid_links to only include relevant URLs
                valid_links = [
                    link for link in valid_links 
                    if link['url'] in relevant_urls
                ]
                
                logger.info(f"Found {len(valid_links)} relevant links")
            
            # Take only the first max_links-1 links (excluding parent)
            valid_links = valid_links[:max_links-1]
            
            # Add parent URL as first link
            links = [url] + [link['url'] for link in valid_links]
            
            # Create output directory if it doesn't exist
            output_dir = "output"
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_filename = f"scraped_content_{timestamp}.zip"
            zip_path = os.path.join(output_dir, zip_filename)
            
            # Create zip file
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for i, link in enumerate(links):
                    try:
                        await page.goto(link)
                        content = await page.content()
                        visible_text = extract_visible_text(content)
                        
                        # Get page title
                        title = await page.title()
                        safe_title = "".join(c if c.isalnum() else "_" for c in title)
                        
                        # Process content in batches for summarization
                        batch_size = 4000  # Process in 4000 char chunks
                        summaries = []
                        
                        for j in range(0, len(visible_text), batch_size):
                            batch = visible_text[j:j + batch_size]
                            summary_prompt = f"""
                            Summarize the following content, focusing on key information and main points.
                            {f'Additional context for summarization: {context}' if context else ''}
                            
                            Content:
                            {batch}
                            
                            Provide a concise summary that captures the essential information.
                            """
                            
                            response = client.chat.completions.create(
                                model="gpt-4-turbo-preview",
                                messages=[{"role": "user", "content": summary_prompt}]
                            )
                            
                            batch_summary = response.choices[0].message.content
                            summaries.append(batch_summary)
                        
                        # Combine all batch summaries into a final summary
                        if len(summaries) > 1:
                            final_summary_prompt = f"""
                            Combine these partial summaries into one cohesive summary:
                            {chr(10).join(summaries)}
                            
                            {f'Additional context for final summary: {context}' if context else ''}
                            
                            Provide a final, well-structured summary that captures all key points.
                            """
                            
                            response = client.chat.completions.create(
                                model="gpt-4-turbo-preview",
                                messages=[{"role": "user", "content": final_summary_prompt}]
                            )
                            final_summary = response.choices[0].message.content
                        else:
                            final_summary = summaries[0]
                        
                        # Create a dictionary with metadata, content, and summary
                        data = {
                            'url': link,
                            'title': title,
                            'timestamp': datetime.now().isoformat(),
                            'content': visible_text,
                            'summary': final_summary
                        }
                        
                        # Write content to zip file
                        content_filename = f"page_{i+1}_{safe_title}.json"
                        zipf.writestr(content_filename, json.dumps(data, indent=2))
                        
                        # Write summary to separate file
                        summary_filename = f"page_{i+1}_{safe_title}_summary.txt"
                        zipf.writestr(summary_filename, final_summary)
                        
                        logger.info(f"Successfully scraped and summarized link {i+1}: {link}")
                        
                    except Exception as e:
                        error_msg = f"Error scraping {link}: {str(e)}"
                        logger.error(error_msg)
            
            logger.info(f"Successfully created zip file at {zip_path}")
            await browser.close()
            return get_static_url(zip_filename)
            
        except Exception as e:
            error_msg = f"Error in scrape_multiple_links for {url}: {str(e)}"
            logger.error(error_msg)
            return f"Error: {str(e)}"
        finally:
            await browser.close()

class ToolNameEnum(str, Enum):
    scrape_web_page = "scrape_web_page"
    scrape_multiple_links = "scrape_multiple_links"
    create_csv_file = "create_csv_file"



@function_tool
async def create_agent(name: str, instructions: str, tools: List[ToolNameEnum]) -> str:
    """
    Creates a new agent with specified instructions and a list of tools.

    This function registers an agent in the database by its name, a description of what it is meant to do (instructions), 
    and a list of tools that the agent can use. Each tool must match an existing tool name already stored in the database.

    Args:
        name (str): The name to assign to the agent.
        instructions (str): A textual guide or directive that describes the agent's intended behavior.
        tools (List[ToolNameEnum]): A list of tool names (as enums) that the agent will be equipped with.

    Returns:
        str: Returns "True" if the agent is successfully created. Returns "None" if the creation fails due to an error.

    Note:
        The tool names provided must correspond to existing tools in the database. If none match, the agent may be created without tools.
    """

    try:
        tool_data = list(map(lambda x: x['_id'], db.tools.find({"name": {"$in": tools}})))
        db.agents.insert_one({"name": name, "instructions": instructions, "tools": tool_data})
        return True
    except Exception:
        return None
