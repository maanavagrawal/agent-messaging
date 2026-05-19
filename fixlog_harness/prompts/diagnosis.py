DIAGNOSIS_PROMPT = """You are documenting a bug for a shared knowledge base.

Given the canonical error and the diff that fixed it, write a one-sentence
diagnosis of what was wrong. Be specific and technical. No prose padding.

ERROR: {error_signature}
DIFF: {diff}

One-sentence diagnosis:"""
