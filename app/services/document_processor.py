# 文档处理器
import os
from pypdf import PdfReader
from openpyxl import load_workbook
from app.config import settings
from app.utils.logger import logger

class DocumentProcessor:
    def __init__(self):
        self.max_chunk_size = settings.MAX_CHUNK_SIZE
        self.overlap_ratio = settings.CHUNK_OVERLAP_RATIO
    
    def extract_text(self, file_path: str) -> str:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        try:
            if ext == '.txt' or ext == '.md':
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            elif ext == '.pdf':
                reader = PdfReader(file_path)
                text = ''
                for page in reader.pages:
                    text += page.extract_text() or ''
                return text
            elif ext in ('.xlsx', '.xls'):
                workbook = load_workbook(file_path)
                text = ''
                for sheet in workbook.sheetnames:
                    worksheet = workbook[sheet]
                    for row in worksheet.iter_rows(values_only=True):
                        row_text = ' '.join(str(cell) for cell in row if cell)
                        text += row_text + '\n'
                return text
            else:
                logger.warning(f"不支持的文件格式: {ext}")
                return ''
        except Exception as e:
            logger.error(f"文件解析失败 {file_path}: {str(e)}")
            return ''
    
    def semantic_chunking(self, content: str) -> list:
        chunks = []
        lines = content.split('\n')
        
        current_chunk = ""
        
        for line in lines:
            if line.startswith('#'):
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            elif line.strip() == "":
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = ""
            else:
                if len(current_chunk) + len(line) > self.max_chunk_size:
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        overlap_length = int(len(current_chunk) * self.overlap_ratio)
                        overlap_text = current_chunk[-overlap_length:] if overlap_length > 0 else ""
                        current_chunk = overlap_text + line + "\n"
                    else:
                        current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return [chunk for chunk in chunks if len(chunk.strip()) > 20]

document_processor = DocumentProcessor()