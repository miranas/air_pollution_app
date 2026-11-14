1. The LangGraph agent is complete but CLI-only — Flask has no /api/ask route even though nginx reserves a slow lane for it.
  2. Two agent runtimes coexist: ai/graph.py (primary) and the legacy ReAct loop in ai/agent.py.
  3. SQL safety is three layers deep: read-only DB role, SELECT-only guard, forced LIMIT 100.
  4. /api/latest uses a five-rung cache fallback ladder.
  5. AQI math is duplicated in Python and TypeScript.
  6. CI references docker/Dockerfile.api, which is currently absent from the repo.


