import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.document_processor import document_processor
from app.services.embedding_service import embedding_service
from app.services.chroma_service import chroma_service
from app.utils.logger import logger

def init_knowledge_base(documents_path: str = "../"):
    markdown_files = []
    
    for root, dirs, files in os.walk(documents_path):
        for file in files:
            if file.endswith(".md") and "MY-RAG" not in root:
                full_path = os.path.join(root, file)
                markdown_files.append(full_path)
                logger.info(f"发现文档: {full_path}")
    
    logger.info(f"共发现 {len(markdown_files)} 个Markdown文档")
    
    for file_path in markdown_files:
        try:
            content = document_processor.extract_text(file_path)
            if not content:
                logger.warning(f"跳过空文档: {file_path}")
                continue
            
            chunks = document_processor.semantic_chunking(content)
            logger.info(f"文档 {file_path} 切分为 {len(chunks)} 个块")
            
            embeddings = embedding_service.get_batch_embeddings(chunks)
            
            valid_chunks = []
            valid_embeddings = []
            for chunk, embedding in zip(chunks, embeddings):
                if embedding:
                    valid_chunks.append(chunk)
                    valid_embeddings.append(embedding)
            
            if valid_chunks:
                from uuid import uuid4
                filename = os.path.basename(file_path)
                ids = [f"doc_{uuid4().hex[:8]}_{i}" for i in range(len(valid_chunks))]
                metadatas = [{'filename': filename, 'chunk_index': i} for i in range(len(valid_chunks))]
                
                chroma_service.add_documents(valid_chunks, valid_embeddings, metadatas, ids)
                logger.info(f"成功导入文档: {filename}")
            else:
                logger.error(f"文档 {file_path} 嵌入失败")
        
        except Exception as e:
            logger.error(f"处理文档 {file_path} 失败: {str(e)}")
    
    logger.info(f"知识库初始化完成，共 {chroma_service.count()} 个文档块")

if __name__ == "__main__":
    init_knowledge_base()