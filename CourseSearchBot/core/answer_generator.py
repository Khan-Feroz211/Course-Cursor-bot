"""
core/answer_generator.py
AI Answer Generator — uses search results to generate natural answers.
Extracts relevant context and creates coherent responses for university queries.
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer
import numpy as np

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """
    Generates natural language answers from search results.
    Uses extractive summarization to find most relevant sentences.
    Optionally uses LLMs for abstractive summarization.
    """
    
    def __init__(self, embedding_model: SentenceTransformer):
        self.model = embedding_model
    
    def extract_sentences(self, text: str, num_sentences: int = 3) -> List[str]:
        """Extract the most important sentences from text."""
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        if len(sentences) <= num_sentences:
            return sentences
        
        # Use sentence embeddings to find most relevant ones
        try:
            sentence_embeddings = self.model.encode(sentences, convert_to_tensor=False)
            
            # Calculate importance based on similarity to all other sentences
            importance_scores = np.zeros(len(sentences))
            for i, emb in enumerate(sentence_embeddings):
                similarities = np.linalg.norm(
                    sentence_embeddings - emb, axis=1
                )
                importance_scores[i] = -np.mean(similarities[similarities > 0])
            
            # Get top sentences
            top_indices = np.argsort(importance_scores)[-num_sentences:]
            top_indices = sorted(top_indices)  # Preserve order
            
            return [sentences[i] for i in top_indices]
        except Exception as e:
            logger.warning(f"Sentence extraction failed: {e}. Returning first {num_sentences}.")
            return sentences[:num_sentences]
    
    def generate_answer(
        self,
        query: str,
        search_results: List[Dict[str, Any]],
        max_answer_length: int = 500,
    ) -> Dict[str, Any]:
        """
        Generate an answer from search results.
        
        Args:
            query: The original query
            search_results: List of search result dicts with 'context', 'file', 'page', 'score'
            max_answer_length: Maximum length of generated answer
        
        Returns:
            Dict with 'answer', 'sources', 'confidence'
        """
        if not search_results:
            return {
                "answer": "No relevant information found in the database.",
                "sources": [],
                "confidence": 0.0,
                "method": "no_results"
            }
        
        # Extract key sentences from top results
        all_sentences = []
        source_map = {}  # Map sentence to (file, page, score)
        
        for i, result in enumerate(search_results[:3]):  # Use top 3 results
            sentences = self.extract_sentences(result["context"], num_sentences=2)
            for sentence in sentences:
                all_sentences.append(sentence)
                source_map[sentence] = {
                    "file": result["file"],
                    "page": result["page"],
                    "score": result["score"],
                }
        
        # Score sentences based on relevance to query
        try:
            query_embedding = self.model.encode([query], convert_to_tensor=False)[0]
            sentence_embeddings = self.model.encode(all_sentences, convert_to_tensor=False)
            
            # Calculate relevance scores
            scores = []
            for emb in sentence_embeddings:
                similarity = np.dot(query_embedding, emb) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-7
                )
                scores.append(float(similarity))
            
            # Select top sentences for answer
            top_indices = np.argsort(scores)[-3:][::-1]  # Top 3, reversed order
            answer_sentences = [all_sentences[i] for i in top_indices]
            avg_score = float(np.mean([scores[i] for i in top_indices]))
            
        except Exception as e:
            logger.error(f"Scoring error: {e}")
            answer_sentences = all_sentences[:3]
            avg_score = np.mean([r["score"] for r in search_results[:3]])
        
        # Construct answer
        answer = " ".join(answer_sentences)
        if len(answer) > max_answer_length:
            answer = answer[:max_answer_length] + "..."
        
        # Ensure answer ends with period
        if answer and not answer.endswith("."):
            answer += "."
        
        # Collect sources
        sources = []
        seen = set()
        for i in top_indices:
            if i < len(all_sentences):
                sent = all_sentences[i]
                if sent in source_map:
                    src = source_map[sent]
                    key = (src["file"], src["page"])
                    if key not in seen:
                        sources.append(src)
                        seen.add(key)
        
        return {
            "answer": answer if answer else "No clear answer could be generated.",
            "sources": sources,
            "confidence": min(0.99, float(avg_score)) if avg_score > 0 else 0.0,
            "method": "extractive_summarization",
            "query": query,
        }
    
    def generate_summary(
        self,
        documents: List[str],
        max_length: int = 300,
    ) -> str:
        """Generate a summary of multiple documents."""
        if not documents:
            return "No content to summarize."
        
        # Extract key sentences
        all_sentences = []
        for doc in documents:
            sentences = self.extract_sentences(doc, num_sentences=2)
            all_sentences.extend(sentences)
        
        # Combine most relevant
        summary_sentences = all_sentences[:5]
        summary = " ".join(summary_sentences)
        
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary
