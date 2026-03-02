# Claude Hello World Agent

A minimal agent demonstrating Claude Agent SDK capabilities in a sandboxed environment.

## Local Development

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Run with uv
uv run run_agent.py --prompt "Hello, create a file called test.txt"

# Or read prompt from stdin
echo "List the current directory" | uv run run_agent.py --stdin
```

## Output Format

The agent streams JSON events to stdout:
- `start` - Agent started
- `text` - Text response from Claude
- `tool_use` - Tool execution (Read, Write, Bash, etc.)
- `result` - Final result with stats
- `error` - Error occurred
- `done` - Agent finished

## Docker

```bash
docker build -t claude-hello-world .
docker run -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY claude-hello-world --prompt "Hello"
```
