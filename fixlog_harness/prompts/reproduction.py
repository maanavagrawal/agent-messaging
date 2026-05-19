REPRODUCTION_PROMPT = """You are helping document a bug fix for a shared
knowledge base used by AI coding agents.

You will be given:
1. The canonical error signature that occurred
2. The diff that fixed it
3. The command that was failing before the fix

Your job: produce the minimal shell commands needed to reproduce the
original error state in a fresh Python virtualenv.

The output must:
- Be valid shell commands, one per line
- Set up the project state such that running the failing command
  produces the original error
- Include any necessary file creation, dependency installation, or
  environment setup
- NOT include the fix itself (the reproduction must REPRODUCE the bug)
- NOT include explanation or prose
- NOT include the failing command itself (that's the trigger, separate)

Output ONLY shell commands. No markdown. No comments. No prose.

---

CANONICAL ERROR:
{error_signature}

DIFF (this is the fix; reverse it mentally to understand the broken state):
{diff}

FAILING COMMAND:
{failing_command}

---

Shell commands to set up the broken state:"""
