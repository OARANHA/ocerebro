"""Camada Official do Cerebro: Markdown durável, versionável"""
from .markdown_storage import MarkdownStorage
from .templates import ErrorTemplate, DecisionTemplate

__all__ = ["MarkdownStorage", "ErrorTemplate", "DecisionTemplate"]
