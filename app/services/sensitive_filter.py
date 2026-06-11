# 敏感词过滤服务 - AC自动机实现
import re
from collections import defaultdict
from app.utils.logger import logger

class ACSensitiveFilter:
    """AC自动机敏感词过滤"""
    
    def __init__(self):
        self.word_tree = defaultdict(dict)
        self.fail_pointers = {}
        self.sensitive_words = set()
        self._load_default_words()
    
    def _load_default_words(self):
        """加载默认敏感词库"""
        # 示例敏感词列表（实际使用时应从数据库或配置文件加载）
        default_words = [
            "暴力", "恐怖", "赌博", "毒品", "诈骗",
            "非法", "犯罪", "攻击", "黑客", "病毒",
            "色情", "低俗", "违法", "禁药", "武器"
        ]
        for word in default_words:
            self.add_word(word)
    
    def add_word(self, word: str):
        """添加敏感词到AC自动机"""
        if not word:
            return
        
        self.sensitive_words.add(word)
        current = self.word_tree
        
        for char in word:
            if char not in current:
                current[char] = defaultdict(dict)
            current = current[char]
        
        # 标记单词结束
        current['_is_end'] = True
        current['_word'] = word
    
    def build_fail_pointers(self):
        """构建失败指针"""
        self.fail_pointers = {}
        queue = []
        
        # 第一层节点的失败指针为根节点
        for char in self.word_tree:
            if char not in ['_is_end', '_word']:
                self.fail_pointers[char] = self.word_tree
                queue.append((char, self.word_tree[char]))
        
        # BFS构建失败指针
        while queue:
            parent_char, parent_node = queue.pop(0)
            
            for char in parent_node:
                if char in ['_is_end', '_word']:
                    continue
                
                child_node = parent_node[char]
                fail_node = self.fail_pointers.get(parent_char, self.word_tree)
                
                # 寻找失败指针
                while fail_node and char not in fail_node:
                    fail_node = self.fail_pointers.get(fail_node.get('_parent_char'), self.word_tree)
                
                if fail_node and char in fail_node:
                    self.fail_pointers[char] = fail_node[char]
                else:
                    self.fail_pointers[char] = self.word_tree
                
                queue.append((char, child_node))
    
    def filter_text(self, text: str) -> dict:
        """
        过滤文本中的敏感词
        Args:
            text: 待检测文本
        Returns:
            {
                "has_sensitive": bool,
                "sensitive_words": list,
                "filtered_text": str,
                "positions": list
            }
        """
        if not text:
            return {"has_sensitive": False, "sensitive_words": [], "filtered_text": text, "positions": []}
        
        # 使用简单的正则匹配（实际生产环境应使用完整的AC自动机）
        found_words = []
        positions = []
        
        for word in self.sensitive_words:
            pattern = re.compile(re.escape(word), re.IGNORECASE)
            matches = pattern.finditer(text)
            for match in matches:
                found_words.append(word)
                positions.append((match.start(), match.end()))
        
        # 过滤敏感词（替换为*）
        filtered_text = text
        for word in found_words:
            filtered_text = filtered_text.replace(word, '*' * len(word))
        
        return {
            "has_sensitive": len(found_words) > 0,
            "sensitive_words": found_words,
            "filtered_text": filtered_text,
            "positions": positions
        }
    
    def check_sensitive(self, text: str) -> bool:
        """
        检查文本是否包含敏感词
        Args:
            text: 待检测文本
        Returns:
            是否包含敏感词
        """
        result = self.filter_text(text)
        return result["has_sensitive"]
    
    def load_custom_words(self, words: list):
        """
        加载自定义敏感词列表
        Args:
            words: 敏感词列表
        """
        for word in words:
            self.add_word(word)
        self.build_fail_pointers()
        logger.info(f"已加载 {len(words)} 个自定义敏感词")

# 全局敏感词过滤器
sensitive_filter = ACSensitiveFilter()