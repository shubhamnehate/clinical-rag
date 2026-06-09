from setuptools import setup, find_packages

setup(
    name="clinical-rag",
    version="1.0.0",
    description="Production-grade Clinical RAG System with HIPAA compliance",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "numpy>=1.24.0",
        "pydantic>=2.0.0",
        "python-dotenv>=1.0.0",
        "PyYAML>=6.0",
        "python-dateutil>=2.8.2",
    ],
    extras_require={
        "ml": [
            "sentence-transformers>=2.2.2",
            "scikit-learn>=1.3.0",
            "rank-bm25>=0.2.2",
        ],
        "llm": ["anthropic>=0.39.0"],
        "clinical": ["pydicom>=2.4.0", "hl7>=0.4.5", "pypdf2>=3.0.0"],
        "storage": ["psycopg2-binary>=2.9.7", "redis>=5.0.0", "elasticsearch>=8.10.0"],
        "all": [
            "sentence-transformers>=2.2.2",
            "scikit-learn>=1.3.0",
            "rank-bm25>=0.2.2",
            "anthropic>=0.39.0",
            "pydicom>=2.4.0",
            "hl7>=0.4.5",
            "pypdf2>=3.0.0",
            "psycopg2-binary>=2.9.7",
            "redis>=5.0.0",
            "elasticsearch>=8.10.0",
        ],
    },
)
