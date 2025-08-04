from typing import Dict, Any, List, Optional
import os
from src.core.model_service import ModelService
from src.tools.browser_tools import BrowserTools
from src.utils.logging_config import get_logger, get_agent_logger, log_agent_execution
import asyncio

# Try to import Tavily
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    TavilyClient = None

logger = get_agent_logger("research")

class ResearchAgent:
    """
    Enhanced research agent with Tavily API integration and expanded capabilities.
    Handles web search, information gathering, source credibility assessment, and analysis tasks.
    """
    
    def __init__(self):
        self.model_service = ModelService()
        self.browser_tools = BrowserTools()
        
        # Initialize Tavily client if available
        self.tavily_client = None
        if TAVILY_AVAILABLE and os.getenv("TAVILY_API_KEY"):
            try:
                self.tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
                logger.info("Tavily API client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Tavily client: {e}")
        else:
            logger.info("Tavily API not available - using browser tools only")
        
    def execute_task(self, task_description: str, context: Dict[int, str] = None) -> str:
        logger.info(f"Executing research task: {task_description[:100]}...")
        
        try:
            # Get model for research
            model = self.model_service.get_model_for_agent("research")
            
            # Check if this is a summary task with sufficient context
            is_summary_task = any(keyword in task_description.lower() for keyword in ['summary', 'summarize', 'compile', 'report'])
            has_context = context and len(context) > 0
            
            if is_summary_task and has_context:
                # For summary tasks with existing context, skip web search and use context directly
                logger.info("Summary task with existing context - skipping web search")
                analysis = self._analyze_from_context(task_description, context, model)
                log_agent_execution("research", task_description, analysis)
                return analysis
            else:
                # Determine research strategy
                search_queries = self._generate_search_queries(task_description, model)
                
                # Perform enhanced web searches with multiple sources
                search_results = []
                
                # Try Tavily first for enhanced search
                if self.tavily_client:
                    tavily_results = self._search_with_tavily(search_queries[:3])  # Use top 3 queries
                    search_results.extend(tavily_results)
                    logger.info(f"Using Tavily search, found {len(tavily_results)} results")
                else:
                    # Only use browser tools if Tavily is not available
                    logger.info("Tavily not available, falling back to browser search")
                    for query in search_queries[:3]:  # Limit to 3 searches
                        try:
                            browser_results = self.browser_tools.search_web(query)
                            search_results.extend(browser_results[:3])  # Top 3 results per query
                        except Exception as e:
                            logger.warning(f"Browser search failed for query '{query}': {e}")
                
                # Remove duplicates and assess source credibility
                unique_results = self._deduplicate_and_assess_sources(search_results)
                
                # Analyze and synthesize results
                if unique_results:
                    analysis = self._analyze_search_results_enhanced(
                        task_description, 
                        unique_results, 
                        context or {},
                        model
                    )
                else:
                    # Fallback to knowledge-based response
                    analysis = self._knowledge_based_response(task_description, model)
                
                logger.info(f"Completed research task with {len(unique_results)} unique sources")
                return analysis
            
        except Exception as e:
            log_agent_execution("research", task_description, error=e)
            return f"Research task failed: {str(e)}"
    
    def _search_with_tavily(self, queries: List[str]) -> List[Dict[str, Any]]:
       
        if not self.tavily_client:
            return []
        
        results = []
        
        for query in queries:
            try:
                logger.info(f"Searching with Tavily: {query}")
                
                # Use Tavily search with enhanced parameters
                tavily_response = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",  # More comprehensive search
                    max_results=5,
                    include_answer=True,
                    include_raw_content=True
                )
                
                # Convert Tavily results to standard format
                for result in tavily_response.get('results', []):
                    formatted_result = {
                        'title': result.get('title', 'No title'),
                        'url': result.get('url', ''),
                        'content': result.get('content', ''),
                        'raw_content': result.get('raw_content', ''),
                        'score': result.get('score', 0.0),
                        'source': 'tavily',
                        'published_date': result.get('published_date', ''),
                        'credibility_score': self._assess_source_credibility(result)
                    }
                    results.append(formatted_result)
                
                # Add Tavily's direct answer if available
                if tavily_response.get('answer'):
                    answer_result = {
                        'title': f"Tavily Answer: {query}",
                        'url': 'tavily://answer',
                        'content': tavily_response['answer'],
                        'raw_content': tavily_response['answer'],
                        'score': 1.0,
                        'source': 'tavily_answer',
                        'credibility_score': 0.9  # High credibility for Tavily answers
                    }
                    results.append(answer_result)
                
            except Exception as e:
                logger.warning(f"Tavily search failed for query '{query}': {e}")
                continue
        
        return results
    
    def _deduplicate_and_assess_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        
        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        
        for result in search_results:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                
                # Assess credibility if not already done
                if 'credibility_score' not in result:
                    result['credibility_score'] = self._assess_source_credibility(result)
                
                unique_results.append(result)
        
        # Sort by credibility score (highest first)
        unique_results.sort(key=lambda x: x.get('credibility_score', 0), reverse=True)
        
        # Limit to top 10 most credible sources
        return unique_results[:10]
    
    def _assess_source_credibility(self, result: Dict[str, Any]) -> float:
       
        credibility_score = 0.5  # Base score
        
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        content = result.get('content', '').lower()
        
        # Domain-based credibility assessment
        high_credibility_domains = [
            'edu', 'gov', 'org', 'nature.com', 'science.org', 'ieee.org',
            'acm.org', 'arxiv.org', 'pubmed.ncbi.nlm.nih.gov', 'scholar.google.com',
            'wikipedia.org', 'britannica.com', 'reuters.com', 'bbc.com', 'npr.org'
        ]
        
        medium_credibility_domains = [
            'com', 'net', 'co.uk', 'medium.com', 'forbes.com', 'techcrunch.com',
            'wired.com', 'arstechnica.com', 'stackoverflow.com', 'github.com'
        ]
        
        # Check domain credibility
        for domain in high_credibility_domains:
            if domain in url:
                credibility_score += 0.3
                break
        else:
            for domain in medium_credibility_domains:
                if domain in url:
                    credibility_score += 0.1
                    break
        
        # Content quality indicators
        if len(content) > 500:  # Substantial content
            credibility_score += 0.1
        
        if any(indicator in content for indicator in ['research', 'study', 'analysis', 'data', 'evidence']):
            credibility_score += 0.1
        
        # Title quality indicators
        if not any(spam_indicator in title for spam_indicator in ['click here', 'amazing', 'shocking', 'you won\'t believe']):
            credibility_score += 0.1
        
        # Tavily score integration
        if 'score' in result and result['score'] > 0.7:
            credibility_score += 0.2
        
        # Ensure score is between 0 and 1
        return min(max(credibility_score, 0.0), 1.0)
    
    def _analyze_search_results_enhanced(self, task_description: str, search_results: List[Dict], context: Dict[int, str], model) -> str:
        
        # Prepare search results summary with credibility scores
        results_summary = []
        high_credibility_sources = []
        
        for i, result in enumerate(search_results[:8], 1):  # Limit to top 8
            credibility = result.get('credibility_score', 0.5)
            credibility_indicator = "🟢" if credibility > 0.7 else "🟡" if credibility > 0.5 else "🔴"
            
            summary = f"{i}. {credibility_indicator} **{result.get('title', 'No title')}** (Score: {credibility:.2f})\n"
            summary += f"   Source: {result.get('url', 'No URL')}\n"
            summary += f"   Content: {result.get('content', 'No content')[:300]}...\n"
            
            if result.get('published_date'):
                summary += f"   Published: {result['published_date']}\n"
            
            results_summary.append(summary)
            
            # Track high credibility sources
            if credibility > 0.7:
                high_credibility_sources.append(result)
        
        # Prepare context from previous tasks
        context_summary = ""
        if context:
            context_summary = "\n\nPREVIOUS TASK RESULTS:\n"
            for task_id, result in context.items():
                context_summary += f"Task {task_id}: {result[:200]}...\n"
        
        # Enhanced analysis prompt
        prompt = f"""You are an expert research analyst. Analyze the search results and provide a comprehensive, well-sourced response.

        RESEARCH TASK: {task_description}

        SEARCH RESULTS (with credibility scores):
        {chr(10).join(results_summary)}

        HIGH CREDIBILITY SOURCES: {len(high_credibility_sources)} sources with score > 0.7
        {context_summary}

        ANALYSIS INSTRUCTIONS:
        1. Synthesize information from multiple sources, prioritizing high-credibility sources
        2. Provide accurate, well-structured analysis with clear sections
        3. Include specific citations with credibility indicators
        4. Address the research question comprehensively
        5. Acknowledge any limitations or conflicting information
        6. Highlight key insights and findings
        7. If information is limited, clearly state what's missing

        COMPREHENSIVE ANALYSIS:"""

        try:
            analysis = model.invoke(prompt)
            
            # Add source credibility summary
            credibility_summary = self._generate_credibility_summary(search_results)
            
            return f"{analysis}\n\n---\n\n{credibility_summary}"
            
        except Exception as e:
            logger.error(f"Failed to analyze search results: {e}")
            return f"Analysis failed, but found {len(search_results)} sources with {len(high_credibility_sources)} high-credibility sources."
    
    def _generate_credibility_summary(self, search_results: List[Dict[str, Any]]) -> str:        
        if not search_results:
            return "**Source Assessment:** No sources available."
        
        high_cred = len([r for r in search_results if r.get('credibility_score', 0) > 0.7])
        medium_cred = len([r for r in search_results if 0.5 < r.get('credibility_score', 0) <= 0.7])
        low_cred = len([r for r in search_results if r.get('credibility_score', 0) <= 0.5])
        
        summary = f"**Source Credibility Assessment:**\n"
        summary += f"- 🟢 High credibility sources: {high_cred}\n"
        summary += f"- 🟡 Medium credibility sources: {medium_cred}\n"
        summary += f"- 🔴 Low credibility sources: {low_cred}\n"
        summary += f"- Total sources analyzed: {len(search_results)}\n"
        
        if self.tavily_client:
            tavily_sources = len([r for r in search_results if r.get('source') == 'tavily'])
            summary += f"- Enhanced Tavily sources: {tavily_sources}\n"
        
        return summary

    def _generate_search_queries(self, task_description: str, model) -> List[str]:
        
        prompt = f"""Generate 2-3 effective web search queries for this research task:

        TASK: {task_description}

        Requirements:
        - Create specific, targeted search queries
        - Use relevant keywords and phrases
        - Avoid overly broad or narrow queries
        - Focus on finding authoritative sources

        Return only the search queries, one per line:"""

        try:
            response = model.invoke(prompt)
            queries = [q.strip() for q in response.split('\n') if q.strip()]
            
            # Fallback if parsing fails
            if not queries:
                queries = [task_description]
            
            return queries[:3]  # Max 3 queries
            
        except Exception as e:
            logger.warning(f"Failed to generate search queries: {e}")
            return [task_description]  # Fallback to task description
    
    def _analyze_search_results(self, task_description: str, search_results: List[Dict], context: Dict[int, str], model) -> str:
        
        # Prepare search results summary
        results_summary = []
        for i, result in enumerate(search_results[:10], 1):  # Limit to top 10
            summary = f"{i}. **{result.get('title', 'No title')}**\n"
            summary += f"   Source: {result.get('url', 'No URL')}\n"
            summary += f"   Content: {result.get('content', 'No content')[:200]}...\n"
            results_summary.append(summary)
        
        # Prepare context from previous tasks
        context_summary = ""
        if context:
            context_summary = "\n\nPREVIOUS TASK RESULTS:\n"
            for task_id, result in context.items():
                context_summary += f"Task {task_id}: {result[:200]}...\n"
        
        prompt = f"""You are a research analyst. Analyze the search results and provide a comprehensive response to the research task.

        RESEARCH TASK: {task_description}

        SEARCH RESULTS:
        {chr(10).join(results_summary)}
        {context_summary}

        INSTRUCTIONS:
        1. Synthesize information from multiple sources
        2. Provide accurate, well-structured analysis
        3. Include relevant details and insights
        4. Cite sources when possible
        5. Address the specific research question
        6. If information is limited, acknowledge gaps

        ANALYSIS:"""

        try:
            analysis = model.invoke(prompt)
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to analyze search results: {e}")
            return f"Analysis failed, but found {len(search_results)} relevant sources."
    
    def _knowledge_based_response(self, task_description: str, model) -> str:
        
        prompt = f"""Provide a comprehensive response to this research task using your knowledge:

        TASK: {task_description}

        INSTRUCTIONS:
        1. Use your existing knowledge to address the task
        2. Be thorough and accurate
        3. Acknowledge any limitations in your knowledge
        4. Structure your response clearly
        5. Note that this is based on training data, not current web search

        RESPONSE:"""

        try:
            response = model.invoke(prompt)
            return f"[Knowledge-based response - no web search available]\n\n{response}"
            
        except Exception as e:
            logger.error(f"Knowledge-based response failed: {e}")
            return f"Unable to complete research task: {str(e)}"
    
    def _analyze_from_context(self, task_description: str, context: Dict[int, str], model) -> str:
        
        # Prepare context summary
        context_summary = "\n\nPREVIOUS TASK RESULTS:\n"
        for task_id, result in context.items():
            context_summary += f"Task {task_id}: {result}\n\n"
        
        prompt = f"""You are a research analyst. Create a comprehensive response to the task using ONLY the information from previous task results.

        TASK: {task_description}

        {context_summary}

        INSTRUCTIONS:
        1. Synthesize the information from previous tasks to address the current task
        2. Create a well-structured, comprehensive response
        3. Do not add information not present in the previous task results
        4. If the task asks for a summary, create a clear, organized summary
        5. Use proper formatting with headers, bullet points, and clear sections
        6. Ensure the response directly addresses what was requested

        RESPONSE:"""

        try:
            response = model.invoke(prompt)
            return response
            
        except Exception as e:
            logger.error(f"Context-based analysis failed: {e}")
            return f"Unable to complete analysis from context: {str(e)}"
    
    def analyze_text(self, text: str, analysis_type: str = "general") -> str:
        logger.info(f"Performing {analysis_type} text analysis")
        
        try:
            model = self.model_service.get_model_for_agent("research")
            
            prompt = f"""Analyze the following text and provide insights:

            TEXT TO ANALYZE:
            {text}

            ANALYSIS TYPE: {analysis_type}

            Provide a structured analysis including:
            1. Key themes and topics
            2. Important insights
            3. Summary of main points
            4. Relevant conclusions

            ANALYSIS:"""

            analysis = model.invoke(prompt)
            return analysis
            
        except Exception as e:
            logger.error(f"Text analysis failed: {e}")
            return f"Text analysis failed: {str(e)}"
    
    def summarize_content(self, content: str, max_length: int = 500) -> str:
        logger.info(f"Summarizing content to ~{max_length} characters")
        
        try:
            model = self.model_service.get_model_for_agent("research")
            
            prompt = f"""Summarize the following content in approximately {max_length} characters:

            CONTENT:
            {content}

            REQUIREMENTS:
            - Capture key points and main ideas
            - Maintain accuracy and context
            - Use clear, concise language
            - Stay within the character limit

            SUMMARY:"""

            summary = model.invoke(prompt)
            return summary
            
        except Exception as e:
            logger.error(f"Content summarization failed: {e}")
            return f"Summarization failed: {str(e)}"