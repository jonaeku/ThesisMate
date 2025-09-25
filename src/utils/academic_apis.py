import requests
import xml.etree.ElementTree as ET
import time
from typing import List
from src.models.models import Paper

def rate_limit(seconds: float):
    """Simple rate limiting decorator"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            time.sleep(seconds)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limit(3.0)  # arXiv requires 3 seconds between requests
def search_arxiv(query: str, max_results: int = 20) -> List[Paper]:
    """Search arXiv API - No authentication required"""
    url = "http://export.arxiv.org/api/query"
    params = {
        'search_query': f'all:{query}',
        'start': 0,
        'max_results': max_results
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        papers = []
        
        # arXiv uses Atom namespace
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        for entry in root.findall('atom:entry', ns):
            try:
                title = entry.find('atom:title', ns).text.strip().replace('\n', ' ')
                
                # Get authors
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns)
                    if name is not None:
                        authors.append(name.text)
                
                # Get abstract
                summary = entry.find('atom:summary', ns)
                abstract = summary.text.strip().replace('\n', ' ') if summary is not None else ""
                
                # Get URL
                url_elem = entry.find('atom:id', ns)
                paper_url = url_elem.text if url_elem is not None else ""
                
                # Get year from published date
                published = entry.find('atom:published', ns)
                year = 2024  # default
                if published is not None:
                    try:
                        year = int(published.text[:4])
                    except:
                        pass
                
                # Generate simple BibTeX
                bibtex = generate_bibtex_arxiv(title, authors, year, paper_url)
                
                paper = Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=paper_url,
                    bibtex=bibtex,
                    year=year,
                    source="arxiv"
                )
                papers.append(paper)
                
            except Exception as e:
                print(f"Error parsing arXiv entry: {e}")
                continue
        
        return papers
        
    except Exception as e:
        print(f"Error searching arXiv: {e}")
        return []

@rate_limit(0.02)  # CrossRef allows 50/second, so 0.02s = safe
def search_crossref(query: str, max_results: int = 20) -> List[Paper]:
    """Search CrossRef API - No authentication required"""
    url = "https://api.crossref.org/works"
    params = {
        'query': query,
        'rows': max_results
    }
    headers = {
        'User-Agent': 'ThesisMate/0.1.0 (mailto:research@thesismate.com)'
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        papers = []
        
        for item in data.get('message', {}).get('items', []):
            try:
                title = ' '.join(item.get('title', [''])[0].split())
                
                # Get authors
                authors = []
                for author in item.get('author', []):
                    given = author.get('given', '')
                    family = author.get('family', '')
                    if given and family:
                        authors.append(f"{given} {family}")
                    elif family:
                        authors.append(family)
                
                # Get abstract (often not available in CrossRef)
                abstract = item.get('abstract', 'Abstract not available')
                if abstract and len(abstract) > 500:
                    abstract = abstract[:500] + "..."
                
                # Get URL
                paper_url = item.get('URL', '')
                
                # Get year
                year = 2024  # default
                published = item.get('published-print') or item.get('published-online')
                if published and 'date-parts' in published:
                    try:
                        year = published['date-parts'][0][0]
                    except:
                        pass
                
                # Get DOI
                doi = item.get('DOI', '')
                
                # Generate BibTeX
                bibtex = generate_bibtex_crossref(title, authors, year, doi, item)
                
                paper = Paper(
                    title=title,
                    authors=authors,
                    abstract=abstract,
                    url=paper_url,
                    bibtex=bibtex,
                    year=year,
                    source="crossref",
                    doi=doi
                )
                papers.append(paper)
                
            except Exception as e:
                print(f"Error parsing CrossRef entry: {e}")
                continue
        
        return papers
        
    except Exception as e:
        print(f"Error searching CrossRef: {e}")
        return []

def search_papers(query: str, max_results: int = 40) -> List[Paper]:
    """Search both arXiv and CrossRef, combine and deduplicate results"""
    all_papers = []
    per_api = max_results // 2
    
    print(f"Searching for '{query}' across academic databases...")
    
    # Search arXiv
    try:
        print("Searching arXiv...")
        arxiv_papers = search_arxiv(query, per_api)
        all_papers.extend(arxiv_papers)
        print(f"Found {len(arxiv_papers)} papers from arXiv")
    except Exception as e:
        print(f"arXiv search failed: {e}")
    
    # Search CrossRef
    try:
        print("Searching CrossRef...")
        crossref_papers = search_crossref(query, per_api)
        all_papers.extend(crossref_papers)
        print(f"Found {len(crossref_papers)} papers from CrossRef")
    except Exception as e:
        print(f"CrossRef search failed: {e}")
    
    # Simple deduplication by title
    unique_papers = deduplicate_papers(all_papers)
    print(f"Total unique papers found: {len(unique_papers)}")
    
    return unique_papers

def deduplicate_papers(papers: List[Paper]) -> List[Paper]:
    """Remove duplicate papers based on title similarity"""
    seen_titles = set()
    unique_papers = []
    
    for paper in papers:
        # Normalize title for comparison
        normalized_title = paper.title.lower().strip().replace(' ', '').replace('-', '')
        
        if normalized_title not in seen_titles:
            seen_titles.add(normalized_title)
            unique_papers.append(paper)
    
    return unique_papers

# BibTeX generation helpers
def generate_bibtex_arxiv(title: str, authors: List[str], year: int, url: str) -> str:
    """Generate BibTeX for arXiv paper"""
    author_str = ' and '.join(authors) if authors else 'Unknown'
    key = title.split()[0].lower() if title else 'unknown'
    
    return f"""@article{{{key}{year},
  title={{{title}}},
  author={{{author_str}}},
  year={{{year}}},
  url={{{url}}},
  note={{arXiv preprint}}
}}"""

def generate_bibtex_crossref(title: str, authors: List[str], year: int, doi: str, item: dict) -> str:
    """Generate BibTeX for CrossRef paper"""
    author_str = ' and '.join(authors) if authors else 'Unknown'
    key = title.split()[0].lower() if title else 'unknown'
    
    # Try to get journal name
    journal = ''
    container_title = item.get('container-title', [])
    if container_title:
        journal = container_title[0]
    
    bibtex = f"""@article{{{key}{year},
  title={{{title}}},
  author={{{author_str}}},
  year={{{year}}}"""
    
    if journal:
        bibtex += f",\n  journal={{{journal}}}"
    if doi:
        bibtex += f",\n  doi={{{doi}}}"
    
    bibtex += "\n}"
    return bibtex