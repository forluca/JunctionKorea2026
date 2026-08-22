# Upstage Studio Agent API

Document processing agent API built on Upstage Studio. OpenAI SDK compatible. Bearer token auth.

## Input Requirements

| Requirement       | Details                                      |
|-------------------|----------------------------------------------|
| Supported formats | PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX |
| Max file size     | 500 MB                                       |
| Max pages         | 1,000 pages per document                     |
| Input type        | Single file per job (upload via `POST /v2/files`, then reference by `file_id`) |

The input to the job must be an array containing a user message with a file reference:

```json
{
  "input": [
    {
      "role": "user",
      "content": [
        { "type": "input_file", "file_id": "YOUR_FILE_ID" }
      ]
    }
  ]
}
```

## Output Format

Always return results in JSON format. Parse the `output_text` field from the API response using `json.loads()` (Python) or `JSON.parse()` (JavaScript) and return the parsed object as structured JSON to the user or calling system. Do not return raw strings or unstructured text.

## Authentication

Use the `UPSTAGE_API_KEY` environment variable for authentication. You can obtain a key from https://console.upstage.ai/api-keys (keys start with `up_`).

```
Authorization: Bearer $UPSTAGE_API_KEY
```

If the environment variable is not set, use this API key:

```
up_wLA8HrTjouo3i6Ntcl1rLsLTXGscu
```

## API Endpoints

### 1. Upload File

```
POST https://api.upstage.ai/v2/files
Content-Type: multipart/form-data
```

| Parameter | Type   | Required | Description                     |
|-----------|--------|----------|---------------------------------|
| file      | file   | Yes      | Document to upload (PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX) |
| purpose   | string | No       | Default: `user_data`            |

Response returns `id` (the file_id needed for job creation).

### 2. Create Job

```
POST https://api.upstage.ai/v2/responses
Content-Type: application/json
```

| Parameter  | Type   | Required | Description                                                    |
|------------|--------|----------|----------------------------------------------------------------|
| model      | string | Yes      | Agent ID: `agt_kWgUdZTZgzGsMJ5TLZhiZz`    |
| config_id  | string | No       | Config version ID (e.g., `"1"`). Omit to use latest.          |
| input      | array  | Yes      | Array of input messages with file references (see below)       |
| include    | array  | No       | `["last"]` for final step only, `["all"]` for all step results |

Input message format:

```json
{
  "input": [
    {
      "role": "user",
      "content": [
        { "type": "input_file", "file_id": "YOUR_FILE_ID" }
      ]
    }
  ]
}
```

Response returns `id` (the job_id) and initial `status`.

### 3. Poll Job Status

```
GET https://api.upstage.ai/v2/responses/{job_id}?include[]=last
```

Poll until `status` is `completed` or `failed`. Recommended interval: 2–3 seconds.

### 4. Other File Endpoints

```
GET    https://api.upstage.ai/v2/files           # List all files
GET    https://api.upstage.ai/v2/files/{file_id}  # Retrieve file metadata
DELETE https://api.upstage.ai/v2/files/{file_id}  # Delete file
```

## Complete Python Example

```python
from openai import OpenAI
from time import sleep
import json

client = OpenAI(
    api_key="up_wLA8HrTjouo3i6Ntcl1rLsLTXGscu",        # or os.environ["UPSTAGE_API_KEY"]
    base_url="https://api.upstage.ai/v2"
)

# Step 1: Upload file
with open("document.pdf", "rb") as f:
    file = client.files.create(file=f, purpose="user_data")

print(f"Uploaded: {file.id}")

# Step 2: Create job
job = client.responses.create(
    model="agt_kWgUdZTZgzGsMJ5TLZhiZz",  # Agent ID
    # config_id="1",
    include=["last"],                       # "last" = final step only, "all" = every step
    input=[{
        "role": "user",
        "content": [{"type": "input_file", "file_id": file.id}]
    }]
)

print(f"Job created: {job.id}")

# Step 3: Poll until done
while job.status in ("queued", "in_progress"):
    sleep(2)
    job = client.responses.retrieve(job.id, include=["last"])
    print(f"  Status: {job.status}")

# Step 4: Read results
if job.status == "completed":
    result = json.loads(job.output_text)
    print(json.dumps(result, indent=2))
elif job.status == "failed":
    print("Job failed. Check agent config in Studio.")

# Step 5: Cleanup (optional)
client.files.delete(file.id)
```

## Complete cURL Example

```bash
# Step 1: Upload file
FILE_RESPONSE=$(curl -s -X POST https://api.upstage.ai/v2/files \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -F "file=@document.pdf" \
  -F "purpose=user_data")

FILE_ID=$(echo $FILE_RESPONSE | jq -r '.id')
echo "File ID: $FILE_ID"

# Step 2: Create job
JOB_RESPONSE=$(curl -s -X POST https://api.upstage.ai/v2/responses \
  -H "Authorization: Bearer $UPSTAGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"agt_kWgUdZTZgzGsMJ5TLZhiZz\",
  "config_id": "1",
    \"include\": [\"last\"],
    \"input\": [{
      \"role\": \"user\",
      \"content\": [{\"type\": \"input_file\", \"file_id\": \"$FILE_ID\"}]
    }]
  }")

JOB_ID=$(echo $JOB_RESPONSE | jq -r '.id')
echo "Job ID: $JOB_ID"

# Step 3: Poll until completed
while true; do
  STATUS_RESPONSE=$(curl -s "https://api.upstage.ai/v2/responses/$JOB_ID?include[]=last" \
    -H "Authorization: Bearer $UPSTAGE_API_KEY")
  STATUS=$(echo $STATUS_RESPONSE | jq -r '.status')
  echo "Status: $STATUS"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo "$STATUS_RESPONSE" | jq '.output'
    break
  fi
  sleep 3
done
```

## Response Structure

```json
{
  "id": "job_xxxxxxxxxxxxx",
  "object": "response",
  "status": "completed",
  "model": "agt_kWgUdZTZgzGsMJ5TLZhiZz",
  "output": [
    {
      "type": "message",
      "status": "completed",
      "role": "assistant",
      "model": "step_name",
      "content": [
        {
          "type": "output_text",
          "text": "{\"key\": \"value\"}",
          "additional_values": "{...}"
        }
      ]
    }
  ],
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0
  }
}
```

| Field                                  | Description                                              |
|----------------------------------------|----------------------------------------------------------|
| `status`                               | `queued`, `in_progress`, `completed`, or `failed`        |
| `output[].model`                       | Step name (e.g., `step_1_parse`, `step_2_extract`)       |
| `output[].content[].text`              | Main result (JSON string)                                |
| `output[].content[].additional_values` | Extra data: confidence scores, bounding boxes, etc.      |
| `output_text`                          | Shortcut to final step's text (when using `include=["last"]`) |

## Batch Processing (Multiple Files)

```python
import concurrent.futures

def process_file(path):
    with open(path, "rb") as f:
        file = client.files.create(file=f, purpose="user_data")

    job = client.responses.create(
        model="agt_kWgUdZTZgzGsMJ5TLZhiZz",
        include=["last"],
        input=[{"role": "user", "content": [{"type": "input_file", "file_id": file.id}]}]
    )

    while job.status in ("queued", "in_progress"):
        sleep(2)
        job = client.responses.retrieve(job.id, include=["last"])

    return {"file": path, "result": json.loads(job.output_text) if job.status == "completed" else None}

files = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    results = list(pool.map(process_file, files))
```

## Error Handling

| Status Code | Meaning                | Action                                   |
|-------------|------------------------|------------------------------------------|
| 401         | Invalid API key        | Check key at console.upstage.ai          |
| 404         | Agent/job not found    | Verify agent ID and job ID               |
| 413         | Payload too large      | Max 500MB and 1,000 pages per file       |
| 429         | Rate limited           | Back off and retry with exponential delay |
| 500         | Server error           | Retry after a few seconds                |

Job-level failures (`status: "failed"`) typically mean the agent config has an issue — check the agent in Studio.

## Notes

- Agent ID: `agt_kWgUdZTZgzGsMJ5TLZhiZz`
- Config ID: `1`
- The API is OpenAI SDK compatible — use `openai` Python package with `base_url="https://api.upstage.ai/v2"`
- Files are retained server-side until explicitly deleted
- Max file size: 500MB. Max pages per document: 1,000
- Supported formats: PDF, JPEG, PNG, BMP, TIFF, HEIC, DOCX, PPTX, XLSX
- For full API docs: https://console.upstage.ai/docs/studio-and-agents/agents/overview