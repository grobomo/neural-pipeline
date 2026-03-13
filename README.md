# News Scraper

A Python package for scraping news articles from multiple news sources including Hacker News and BBC News.

## Features

- Modular architecture with abstract base scraper class
- Support for multiple news sources (Hacker News, BBC News)
- CLI interface for easy usage
- Multiple output formats (text, JSON)
- Configurable article limits and request timeouts

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Command Line Interface

Basic usage with default options (Hacker News, text format, 10 articles):

```bash
python -m news_scraper.cli
```

### Specifying a News Source

Scrape from BBC News instead:

```bash
python -m news_scraper.cli --source bbc
```

### Output Formats

Get results in JSON format:

```bash
python -m news_scraper.cli --format json
```

Get results in text format (default):

```bash
python -m news_scraper.cli --format text
```

### Limit Articles

Display only the first 5 articles:

```bash
python -m news_scraper.cli --limit 5
```

### Combined Example

Scrape BBC News, output as JSON, limit to 20 articles:

```bash
python -m news_scraper.cli --source bbc --format json --limit 20
```

## Programmatic Usage

You can also use the scrapers directly in your Python code:

```python
from news_scraper.hacker_news import HackerNewsScraper
from news_scraper.bbc import BBCScraper

# Scrape Hacker News
hn_scraper = HackerNewsScraper()
articles = hn_scraper.scrape()

for article in articles[:5]:
    print(f"{article.title}")
    print(f"  URL: {article.url}\n")

# Scrape BBC News
bbc_scraper = BBCScraper()
articles = bbc_scraper.scrape()

for article in articles[:5]:
    print(f"{article.title}")
    print(f"  URL: {article.url}\n")
```

## Architecture

### Article Class

The `Article` dataclass represents a news article with the following fields:

- `title` (str): Article headline
- `url` (str): Link to the article
- `summary` (str): Article summary or excerpt
- `source` (str): News source name
- `published_at` (Optional[str]): Publication date/time
- `author` (Optional[str]): Author name

Methods:
- `to_dict()`: Convert article to a dictionary

### BaseScraper Class

Abstract base class that all scrapers inherit from:

- `__init__(timeout=10)`: Initialize with request timeout
- `scrape()`: Abstract method to fetch and parse articles
- `_fetch(url)`: Helper method to fetch URL content with error handling
- `ScraperError`: Custom exception for scraper failures

### Available Scrapers

#### HackerNewsScraper

Scrapes the front page of Hacker News (https://news.ycombinator.com) and extracts story titles and links.

```python
from news_scraper.hacker_news import HackerNewsScraper

scraper = HackerNewsScraper(timeout=15)  # Optional custom timeout
articles = scraper.scrape()
```

#### BBCScraper

Scrapes BBC News homepage (https://www.bbc.com/news) and extracts article headlines.

```python
from news_scraper.bbc import BBCScraper

scraper = BBCScraper(timeout=15)  # Optional custom timeout
articles = scraper.scrape()
```

## Extending with New Scrapers

To add a new scraper for a different news source:

1. Create a new Python file in the `news_scraper/` directory
2. Import `BaseScraper` and `Article` from the base modules
3. Create a class that inherits from `BaseScraper`
4. Implement the `scrape()` method using `_fetch()` to get HTML
5. Use BeautifulSoup to parse the HTML and extract article information
6. Return a list of `Article` objects

Example:

```python
from bs4 import BeautifulSoup
from .article import Article
from .base import BaseScraper, ScraperError

class CustomNewsScraper(BaseScraper):
    SOURCE = 'Custom News'
    URL = 'https://example.com/news'

    def scrape(self):
        try:
            html = self._fetch(self.URL)
            soup = BeautifulSoup(html, 'lxml')
            articles = []
            
            # Parse HTML and create Article objects
            for item in soup.select('.article'):
                article = Article(
                    title=item.select_one('.title').text.strip(),
                    url=item.select_one('a').get('href', ''),
                    summary='',
                    source=self.SOURCE,
                )
                articles.append(article)
            
            return articles
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(f"Error scraping Custom News: {str(e)}")
```

Then update the CLI to include your new scraper in `cli.py`.

## Error Handling

The package uses `ScraperError` for all scraping-related errors. When using the CLI, errors are printed to stderr and the program exits with code 1.

```python
from news_scraper.base import ScraperError

try:
    scraper = HackerNewsScraper()
    articles = scraper.scrape()
except ScraperError as e:
    print(f"Scraping failed: {e}")
```

## Requirements

- Python 3.7+
- requests >= 2.28.0
- beautifulsoup4 >= 4.11.0
- lxml >= 4.9.0

## License

MIT
