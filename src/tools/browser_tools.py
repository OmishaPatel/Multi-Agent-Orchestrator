from typing import List, Dict, Any, Optional
from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain_core.tools import Tool
from src.utils.logging_config import get_logger, get_service_logger
import re
import time

logger = get_service_logger("browser_tools")

class BrowserTools:
    """
    Browser tools for web search and content retrieval.
    Provides web search capabilities using DuckDuckGo and other search engines.
    """
    
    def __init__(self):
        self.ddg_search = DuckDuckGoSearchRun()
        logger.info("BrowserTools initialized with DuckDuckGo search")
    
    def search_web(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Search the web using DuckDuckGo and return structured results.
        
        Args:
            query: Search query string
            max_results: Maximum number of results to return
            
        Returns:
            List of dictionaries containing search results with title, url, and content
        """
        logger.info(f"Searching web for: {query}")
        
        try:
            # Perform DuckDuckGo search
            raw_results = self.ddg_search.run(query)
            
            # Parse and structure the results
            structured_results = self._parse_ddg_results(raw_results, max_results)
            
            logger.info(f"Found {len(structured_results)} search results")
            return structured_results
            
        except Exception as e:
            logger.error(f"Web search failed for query '{query}': {e}")
            return []
    
    def _parse_ddg_results(self, raw_results: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Parse raw DuckDuckGo search results into structured format.
        
        Args:
            raw_results: Raw search results string from DuckDuckGo
            max_results: Maximum number of results to parse
            
        Returns:
            List of structured result dictionaries
        """
        results = []
        
        try:
            # Split results by common separators
            # DuckDuckGo results are typically separated by newlines or specific patterns
            result_blocks = self._split_search_results(raw_results)
            
            for i, block in enumerate(result_blocks[:max_results]):
                if not block.strip():
                    continue
                
                # Extract title, URL, and content from each block
                parsed_result = self._extract_result_components(block, i)
                if parsed_result:
                    results.append(parsed_result)
            
        except Exception as e:
            logger.warning(f"Failed to parse search results: {e}")
            # Fallback: return raw results as single item
            if raw_results.strip():
                results.append({
                    'title': 'Search Results',
                    'url': 'ddg://search',
                    'content': raw_results[:500],
                    'raw_content': raw_results,
                    'score': 0.5,
                    'source': 'duckduckgo'
                })
        
        return results
    
    def _split_search_results(self, raw_results: str) -> List[str]:
        
        # Try different splitting strategies
        
        # Strategy 1: Split by double newlines
        blocks = raw_results.split('\n\n')
        if len(blocks) > 1:
            return blocks
        
        # Strategy 2: Split by single newlines and group
        lines = raw_results.split('\n')
        blocks = []
        current_block = []
        
        for line in lines:
            line = line.strip()
            if not line:
                if current_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
            else:
                current_block.append(line)
        
        if current_block:
            blocks.append('\n'.join(current_block))
        
        # Strategy 3: If still no good blocks, split by sentences
        if len(blocks) <= 1 and len(raw_results) > 200:
            sentences = re.split(r'[.!?]+', raw_results)
            blocks = [s.strip() for s in sentences if len(s.strip()) > 50]
        
        return blocks if blocks else [raw_results]
    
    def _extract_result_components(self, result_block: str, index: int) -> Optional[Dict[str, Any]]:
        
        try:
            # Initialize result structure
            result = {
                'title': f'Search Result {index + 1}',
                'url': 'ddg://result',
                'content': result_block.strip(),
                'raw_content': result_block,
                'score': 0.6,
                'source': 'duckduckgo'
            }
            
            # Try to extract URL patterns
            url_patterns = [
                r'https?://[^\s\)]+',
                r'www\.[^\s\)]+',
                r'[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s\)]*'
            ]
            
            for pattern in url_patterns:
                urls = re.findall(pattern, result_block)
                if urls:
                    result['url'] = urls[0]
                    break
            
            # Try to extract title (first line or sentence)
            lines = result_block.split('\n')
            if lines:
                first_line = lines[0].strip()
                if len(first_line) > 10 and len(first_line) < 200:
                    result['title'] = first_line
                    # Use remaining content as description
                    if len(lines) > 1:
                        result['content'] = '\n'.join(lines[1:]).strip()
            
            # Ensure content is not too long
            if len(result['content']) > 1000:
                result['content'] = result['content'][:1000] + '...'
            
            # Skip if content is too short
            if len(result['content']) < 20:
                return None
            
            return result
            
        except Exception as e:
            logger.warning(f"Failed to extract components from result block: {e}")
            return None
    
    def get_page_content(self, url: str) -> Optional[str]:
        """
        Get content from a specific URL (placeholder for future implementation).
        
        Args:
            url: URL to fetch content from
            
        Returns:
            Page content as string, or None if failed
        """
        logger.warning(f"get_page_content not implemented for URL: {url}")
        return None
    
    def search_with_filters(self, query: str, site: str = None, filetype: str = None) -> List[Dict[str, Any]]:
        """
        Search with additional filters.
        
        Args:
            query: Search query
            site: Specific site to search (e.g., "github.com")
            filetype: File type filter (e.g., "pdf")
            
        Returns:
            List of filtered search results
        """
        # Modify query with filters
        filtered_query = query
        
        if site:
            filtered_query += f" site:{site}"
        
        if filetype:
            filtered_query += f" filetype:{filetype}"
        
        logger.info(f"Searching with filters: {filtered_query}")
        return self.search_web(filtered_query)


# Legacy compatibility - keep existing tools for backward compatibility
search_tool = DuckDuckGoSearchRun()

browser_tool = Tool(
    name="web_search",
    func=search_tool.run,
    description="""
    A tool to search the internet for information.
    Use this to find facts, data, code examples, or any other information
    needed to complete the user's request.
    Input should be a clear and concise search query.
    """
)