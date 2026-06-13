"""Example API requests and responses"""

# Example 1: Memory Ingestion
INGEST_REQUEST = {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "conversation": """
    I'm building an AI startup called Nexus, focused on inference optimization.
    My goal is to reduce latency for LLM inference by 50% using novel quantization techniques.
    I prefer concise technical answers and deep dives into system design.
    I'm currently preparing for backend engineering interviews and need help with distributed systems.
    I love building scalable infrastructure and I'm passionate about AI systems.
    """,
    "session_metadata": {}
}

INGEST_RESPONSE = {
    "extracted_memories": [
        {
            "memory_type": "identity",
            "content": "Building AI startup called Nexus focused on inference optimization",
            "summary": "User is building inference optimization startup",
            "importance_score": 0.94,
            "metadata": {"extraction_method": "llm"}
        },
        {
            "memory_type": "identity",
            "content": "Goal is to reduce LLM inference latency by 50% using novel quantization",
            "summary": "Technical goal: 50% latency reduction via quantization",
            "importance_score": 0.91,
            "metadata": {"extraction_method": "llm"}
        },
        {
            "memory_type": "procedural",
            "content": "Prefers concise technical answers and deep dives into system design",
            "summary": "Prefers technical depth and conciseness",
            "importance_score": 0.87,
            "metadata": {"extraction_method": "llm"}
        },
        {
            "memory_type": "semantic",
            "content": "Passionate about building scalable infrastructure and AI systems",
            "summary": "Interested in scalable infrastructure and AI",
            "importance_score": 0.85,
            "metadata": {"extraction_method": "llm"}
        },
        {
            "memory_type": "identity",
            "content": "Preparing for backend engineering interviews and needs help with distributed systems",
            "summary": "Interview preparation focus on distributed systems",
            "importance_score": 0.82,
            "metadata": {"extraction_method": "llm"}
        }
    ],
    "total_tokens_saved": 420,
    "ingestion_latency_ms": 1842.35
}


# Example 2: Memory Retrieval
RETRIEVAL_REQUEST = {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "query": "What quantization techniques should I consider for inference optimization?",
    "top_k": 10,
    "memory_types": None,
    "min_importance": 0.3
}

RETRIEVAL_RESPONSE = {
    "retrieved_memories": [
        {
            "id": "650e8400-e29b-41d4-a716-446655440000",
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "memory_type": "identity",
            "content": "Goal is to reduce LLM inference latency by 50% using novel quantization",
            "summary": "Technical goal: 50% latency reduction via quantization",
            "importance_score": 0.91,
            "reinforcement_count": 0,
            "access_count": 1,
            "last_accessed": "2026-05-13T10:30:00Z",
            "created_at": "2026-05-13T10:00:00Z",
            "updated_at": "2026-05-13T10:30:00Z",
            "metadata": {}
        },
        {
            "id": "750e8400-e29b-41d4-a716-446655440000",
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "memory_type": "identity",
            "content": "Building AI startup called Nexus focused on inference optimization",
            "summary": "User is building inference optimization startup",
            "importance_score": 0.94,
            "reinforcement_count": 0,
            "access_count": 2,
            "last_accessed": "2026-05-13T10:28:00Z",
            "created_at": "2026-05-13T10:00:00Z",
            "updated_at": "2026-05-13T10:28:00Z",
            "metadata": {}
        },
        {
            "id": "850e8400-e29b-41d4-a716-446655440000",
            "user_id": "550e8400-e29b-41d4-a716-446655440000",
            "memory_type": "procedural",
            "content": "Prefers concise technical answers and deep dives into system design",
            "summary": "Prefers technical depth and conciseness",
            "importance_score": 0.87,
            "reinforcement_count": 0,
            "access_count": 1,
            "last_accessed": "2026-05-13T10:32:00Z",
            "created_at": "2026-05-13T10:00:00Z",
            "updated_at": "2026-05-13T10:32:00Z",
            "metadata": {}
        }
    ],
    "compressed_context": {
        "user_profile": "Interaction Style:\n- Prefers concise technical answers and deep dives into system design\n\nUser Profile:\n- Building AI startup called Nexus focused on inference optimization\n- Goal is to reduce LLM inference latency by 50% using novel quantization",
        "relevant_memories": [
            "Goal is to reduce LLM inference latency by 50% using novel quantization",
            "Building AI startup called Nexus focused on inference optimization",
            "Prefers concise technical answers and deep dives into system design"
        ],
        "context_summary": "Query: What quantization techniques should I consider for inference optimization?\n\nRelevant Context:\n- [identity] Goal is to reduce LLM inference latency by 50% using novel quantization\n- [identity] Building AI startup called Nexus focused on inference optimization\n- [procedural] Prefers concise technical answers and deep dives into system design",
        "estimated_tokens": 189
    },
    "retrieval_latency_ms": 523.45,
    "context_token_reduction_percent": 81.2
}


# Example 3: Context Reconstruction for LLM Injection
RECONSTRUCT_REQUEST = {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "query": "I need help designing the inference pipeline for Nexus. What are the critical architectural decisions?",
    "include_procedural": True,
    "context_token_limit": 2000
}

RECONSTRUCT_RESPONSE = {
    "reconstructed_context": """Query: I need help designing the inference pipeline for Nexus. What are the critical architectural decisions?

User Context:
Interaction Style:
- Prefers concise technical answers
- Enjoys deep dives into system design

User Profile:
- Building AI startup Nexus focused on inference optimization
- Goal: 50% latency reduction via novel quantization
- Preparing for backend engineering interviews

Relevant Memories:
- [identity] Building AI startup called Nexus focused on inference optimization
- [identity] Goal is to reduce LLM inference latency by 50% using novel quantization
- [identity] Preparing for backend engineering interviews and needs help with distributed systems
- [procedural] Prefers concise technical answers and deep dives into system design
- [semantic] Passionate about building scalable infrastructure and AI systems""",
    "source_memory_count": 5,
    "estimated_tokens": 256,
    "reconstruction_latency_ms": 412.78
}


# Example 4: Usage with actual LLM call (pseudo-code)
USAGE_EXAMPLE = """
# 1. User query
user_query = "How should I design the inference pipeline?"

# 2. Reconstruct context
response = requests.post(
    "http://localhost:8000/memory/reconstruct",
    json={
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "query": user_query,
        "include_procedural": True,
    }
)

reconstructed_context = response.json()["reconstructed_context"]

# 3. Inject into LLM prompt
llm_prompt = f'''You are an expert AI systems architect.

User Background and Preferences:
{reconstructed_context}

User Question: {user_query}

Provide a concise, technically deep response.'''

# 4. Call LLM (tokens saved by using NeuroWeave context)
response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[{"role": "user", "content": llm_prompt}]
)

# 5. Store new learnings from conversation
new_conversation = f"User asked: {user_query}\\nAssistant response: {response['choices'][0]['message']['content']}"

requests.post(
    "http://localhost:8000/memory/ingest",
    json={
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "conversation": new_conversation
    }
)
"""

if __name__ == "__main__":
    import json
    print("NeuroWeave API Examples")
    print("=" * 50)
    print("\n1. Memory Ingestion Request:")
    print(json.dumps(INGEST_REQUEST, indent=2))
    print("\n2. Memory Ingestion Response:")
    print(json.dumps(INGEST_RESPONSE, indent=2))
    print("\n3. Memory Retrieval Request:")
    print(json.dumps(RETRIEVAL_REQUEST, indent=2))
    print("\n4. Memory Retrieval Response (abbreviated):")
    print(json.dumps(
        {
            "retrieved_memories_count": 3,
            "context_token_reduction_percent": 81.2,
            "retrieval_latency_ms": 523.45
        },
        indent=2
    ))
