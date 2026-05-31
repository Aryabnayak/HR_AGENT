import os
import logging
from typing import List, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import PyPDFLoader, WebBaseLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnterpriseRAGIngestion:
    def __init__(self, persist_directory: str = "./chroma_db"):
        logger.info("Initializing Enterprise RAG via HuggingFace...")
        # Offline, open-source embedding model via HuggingFace
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'} 
        )
        self.vectorstore = Chroma(persist_directory=persist_directory, embedding_function=self.embeddings)
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=250)
        
        # --- NEW LOGIC: Automatically load policies if the file exists ---
        if os.path.exists("company_policies.pdf"):
            try:
                logger.info("Detected company_policies.pdf. Running ingestion...")
                self.ingest_data("company_policies.pdf")
            except Exception as e:
                logger.error(f"Auto-ingestion failed: {e}")

    def _select_loader(self, source_path: str):
        if source_path.startswith("http"): return WebBaseLoader(source_path)
        elif source_path.endswith(".pdf"): return PyPDFLoader(source_path)
        elif source_path.endswith(".txt"): return TextLoader(source_path)
        else: raise ValueError(f"Format unsupported: {source_path}")

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1.5, min=2, max=15))
    def load_documents_with_healing(self, source_path: str) -> List[Document]:
        return self._select_loader(source_path).load()

    def ingest_data(self, source_path: str, metadata_tags: Dict[str, Any] = None) -> str:
        try:
            raw_docs = self.load_documents_with_healing(source_path)
            if metadata_tags:
                for doc in raw_docs: doc.metadata.update(metadata_tags)
            chunked_docs = self.text_splitter.split_documents(raw_docs)
            self.vectorstore.add_documents(chunked_docs)
            return f"Ingested {source_path} ({len(chunked_docs)} chunks)."
        except Exception as e:
            return f"Ingestion Failed. Error: {str(e)}"

rag_pipeline = EnterpriseRAGIngestion()