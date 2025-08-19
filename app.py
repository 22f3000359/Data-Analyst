
import os
import networkx as nx
import re
import json
import base64
import tempfile
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import io
import os
import re
import json
import base64
import tempfile
import subprocess
import logging
from io import BytesIO
from typing import Dict, Any, List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import FastAPI
from dotenv import load_dotenv

import requests
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Optional image conversion
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

from PIL import Image
import pytesseract
try:
    import cv2  # comes from opencv-python-headless
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    PYTESS_AVAILABLE = True
except ImportError:
    PYTESS_AVAILABLE = False

# LangChain / LLM imports (keep as you used)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TDS Data Analyst Agent")

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", 180))


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main HTML interface"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found</h1><p>Please ensure index.html is in the same directory as app.py</p>", status_code=404)




# -----------------------------
# Tools
# -----------------------------

@tool
def scrape_url_to_dataframe(url: str) -> Dict[str, Any]:
    """
    Universal web/data scraper.
    Fetches data from any URL: JSON, CSV, Excel, Parquet, DB files, archives, HTML tables, or dynamic JS-rendered pages.
    Returns a dictionary with status, data, and columns.
    """
    import os, re, tempfile, requests, pandas as pd, duckdb
    from io import BytesIO, StringIO
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.google.com"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "").lower()

        # JSON
        if "application/json" in ctype or url.endswith(".json"):
            df = pd.json_normalize(resp.json())
            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # CSV
        if "text/csv" in ctype or url.endswith(".csv"):
            df = pd.read_csv(BytesIO(resp.content))
            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # Excel
        if any(url.endswith(ext) for ext in (".xls", ".xlsx")) or "spreadsheetml" in ctype:
            df = pd.read_excel(BytesIO(resp.content))
            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # Parquet
        if url.endswith(".parquet") or "parquet" in ctype:
            df = pd.read_parquet(BytesIO(resp.content))
            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # Databases (.db, .duckdb)
        if url.endswith(".db") or url.endswith(".duckdb"):
            tmp_path = tempfile.NamedTemporaryFile(delete=False).name
            with open(tmp_path, "wb") as f:
                f.write(resp.content)
            con = duckdb.connect(database=':memory:')
            con.execute(f"ATTACH '{tmp_path}' AS db")
            tables = con.execute("SHOW TABLES FROM db").fetchdf()
            if not tables.empty:
                table_name = tables.iloc[0, 0]
                df = con.execute(f"SELECT * FROM db.{table_name}").fetchdf()
                con.close()
                os.remove(tmp_path)
                return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # Archives (.tar.gz, .zip)
        if url.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
            import tarfile, zipfile
            content = BytesIO(resp.content)
            if url.endswith(".zip"):
                with zipfile.ZipFile(content, 'r') as z:
                    for name in z.namelist():
                        if name.endswith(".parquet"):
                            df = pd.read_parquet(z.open(name))
                            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
                        if name.endswith(".csv"):
                            df = pd.read_csv(z.open(name))
                            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
            else:
                with tarfile.open(fileobj=content, mode="r:*") as tar:
                    for member in tar.getmembers():
                        if member.name.endswith(".parquet"):
                            df = pd.read_parquet(tar.extractfile(member))
                            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
                        if member.name.endswith(".csv"):
                            df = pd.read_csv(tar.extractfile(member))
                            return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}

        # Static HTML tables
        try:
            tables = pd.read_html(StringIO(resp.text), flavor="lxml")
            if tables:
                df = tables[0]
                return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        except Exception:
            pass

        # Dynamic JS rendering
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=45000)
                page.wait_for_load_state("networkidle")
                html = page.content()
                browser.close()
            tables = pd.read_html(StringIO(html), flavor="lxml")
            if tables:
                df = tables[0]
                return {"status": "success", "data": df.to_dict(orient="records"), "columns": list(df.columns)}
        except Exception:
            pass

        # Plain text fallback
        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text("\n", strip=True)
        return {"status": "success", "data": [{"text": text}], "columns": ["text"]}

    except Exception as e:
        return {"status": "error", "message": str(e)}



# -----------------------------
# Utilities for executing code safely
# -----------------------------
def clean_llm_output(output: str) -> Dict:
    """
    Extract JSON object from LLM output robustly.
    Returns dict or {"error": "..."}
    """
    try:
        if not output:
            return {"error": "Empty LLM output"}
        # remove triple-fence markers if present
        s = re.sub(r"^```(?:json)?\s*", "", output.strip())
        s = re.sub(r"\s*```$", "", s)
        # find outermost JSON object by scanning for balanced braces
        first = s.find("{")
        last = s.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return {"error": "No JSON object found in LLM output", "raw": s}
        candidate = s[first:last+1]
        try:
            return json.loads(candidate)
        except Exception as e:
            # fallback: try last balanced pair scanning backwards
            for i in range(last, first, -1):
                cand = s[first:i+1]
                try:
                    return json.loads(cand)
                except Exception:
                    continue
            return {"error": f"JSON parsing failed: {str(e)}", "raw": candidate}
    except Exception as e:
        return {"error": str(e)}

SCRAPE_FUNC = r'''
from typing import Dict, Any
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

def scrape_url_to_dataframe(url: str) -> Dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5
        )
        response.raise_for_status()
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "data": [],
            "columns": []
        }

    soup = BeautifulSoup(response.text, "html.parser")
    tables = pd.read_html(response.text)

    if tables:
        df = tables[0]  # Take first table
        df.columns = [str(c).strip() for c in df.columns]
        
        # Ensure all columns are unique and string
        df.columns = [str(col) for col in df.columns]

        return {
            "status": "success",
            "data": df.to_dict(orient="records"),
            "columns": list(df.columns)
        }
    else:
        # Fallback to plain text
        text_data = soup.get_text(separator="\n", strip=True)

        # Try to detect possible "keys" from text like Runtime, Genre, etc.
        detected_cols = set(re.findall(r"\b[A-Z][a-zA-Z ]{2,15}\b", text_data))
        df = pd.DataFrame([{}])  # start empty
        for col in detected_cols:
            df[col] = None

        if df.empty:
            df["text"] = [text_data]

        return {
            "status": "success",
            "data": df.to_dict(orient="records"),
            "columns": list(df.columns)
        }
'''


def write_and_run_temp_python(code: str, injected_pickle: str = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Write a temp python file which:
      - provides a safe environment (imports)
      - loads df/from pickle if provided into df and data variables
      - defines a robust plot_to_base64() helper that ensures < 100kB (attempts resizing/conversion)
      - executes the user code (which should populate `results` dict)
      - prints json.dumps({"status":"success","result":results})
    Returns dict with parsed JSON or error details.
    """
    # create file content
    preamble = [
        "import json, sys, gc",
        "import pandas as pd, numpy as np",
        "import matplotlib",
        "matplotlib.use('Agg')",
        "import matplotlib.pyplot as plt",
        "from io import BytesIO",
        "import base64",
    ]
    if PIL_AVAILABLE:
        preamble.append("from PIL import Image")
    # inject df if a pickle path provided
    if injected_pickle:
        preamble.append(f"df = pd.read_pickle(r'''{injected_pickle}''')\n")
        preamble.append("data = df.to_dict(orient='records')\n")
    else:
        # ensure data exists so user code that references data won't break
        preamble.append("data = globals().get('data', {})\n")

    # plot_to_base64 helper that tries to reduce size under 100_000 bytes
    helper = r'''
def plot_to_base64(max_bytes=100000):
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
    buf.seek(0)
    img_bytes = buf.getvalue()
    if len(img_bytes) <= max_bytes:
        return base64.b64encode(img_bytes).decode('ascii')
    # try decreasing dpi/figure size iteratively
    for dpi in [80, 60, 50, 40, 30]:
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=dpi)
        buf.seek(0)
        b = buf.getvalue()
        if len(b) <= max_bytes:
            return base64.b64encode(b).decode('ascii')
    # if Pillow available, try convert to WEBP which is typically smaller
    try:
        from PIL import Image
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=40)
        buf.seek(0)
        im = Image.open(buf)
        out_buf = BytesIO()
        im.save(out_buf, format='WEBP', quality=80, method=6)
        out_buf.seek(0)
        ob = out_buf.getvalue()
        if len(ob) <= max_bytes:
            return base64.b64encode(ob).decode('ascii')
        # try lower quality
        out_buf = BytesIO()
        im.save(out_buf, format='WEBP', quality=60, method=6)
        out_buf.seek(0)
        ob = out_buf.getvalue()
        if len(ob) <= max_bytes:
            return base64.b64encode(ob).decode('ascii')
    except Exception:
        pass
    # as last resort return downsized PNG even if > max_bytes
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=20)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode('ascii')
'''

    # Build the code to write
    script_lines = []
    script_lines.extend(preamble)
    script_lines.append(helper)
    script_lines.append(SCRAPE_FUNC)
    script_lines.append("\nresults = {}\n")
    script_lines.append(code)
    # ensure results printed as json
    script_lines.append("\nprint(json.dumps({'status':'success','result':results}, default=str), flush=True)\n")

    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
    tmp.write("\n".join(script_lines))
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()

    try:
        completed = subprocess.run([sys.executable, tmp_path],
                                   capture_output=True, text=True, timeout=timeout)
        if completed.returncode != 0:
            # collect stderr and stdout for debugging
            return {"status": "error", "message": completed.stderr.strip() or completed.stdout.strip()}
        # parse stdout as json
        out = completed.stdout.strip()
        try:
            parsed = json.loads(out)
            return parsed
        except Exception as e:
            return {"status": "error", "message": f"Could not parse JSON output: {str(e)}", "raw": out}
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Execution timed out"}
    finally:
        try:
            os.unlink(tmp_path)
            if injected_pickle and os.path.exists(injected_pickle):
                os.unlink(injected_pickle)
        except Exception:
            pass


# -----------------------------
# LLM agent setup
# -----------------------------
llm = ChatGoogleGenerativeAI(
    model=os.getenv("GOOGLE_MODEL", "gemini-2.5-pro"),
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# Tools list for agent (LangChain tool decorator returns metadata for the LLM)
tools = [scrape_url_to_dataframe]  # we only expose scraping as a tool; agent will still produce code

# Prompt: instruct agent to call the tool and output JSON only
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a full-stack autonomous data analyst agent.

You will receive:
- A set of **rules** for this request
- One or more **questions**
- An optional **dataset preview**
- A `.txt` file that specifies the required JSON keys and their types.

You must:
1. Follow the provided rules exactly.
2. Return only a valid JSON object — no extra commentary or formatting.
3. The JSON must contain:
   - "keys": [ list of output keys exactly as specified in the .txt file ]
   - "code": "..." (Python code that creates a dict called `results` with each output key as a key and its computed answer as the value)
4. In your Python code, make sure the values are cast to the types specified in the .txt file:
   - `number` → float
   - `integer` / `int` → int
   - `string` → str
   - `bar_chart` / `plt` etc. → base64 PNG string under 100kB (use plot_to_base64()).
5. Do not return the full question text as a key. Always use the JSON key specified in the `.txt`.
6. Always define variables before use. Code must run without errors.
"""),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(
    llm=llm,
    tools=[scrape_url_to_dataframe],  # let the agent call tools if it wants; we will also pre-process scrapes
    prompt=prompt
)

agent_executor = AgentExecutor(
    agent=agent,
    tools=[scrape_url_to_dataframe],
    verbose=True,
    max_iterations=3,
    early_stopping_method="generate",
    handle_parsing_errors=True,
    return_intermediate_steps=False
)


# -----------------------------
# Runner: orchestrates agent -> pre-scrape inject -> execute
# -----------------------------

from fastapi import Request

@app.post("/api")
async def analyze_data(request: Request):
    try:
        form = await request.form()
        questions_file = None
        data_file = None

        for key, val in form.items():
            if hasattr(val, "filename") and val.filename:  # it's a file
                fname = val.filename.lower()
                if fname.endswith(".txt") and questions_file is None:
                    questions_file = val
                else:
                    data_file = val

        if not questions_file:
            raise HTTPException(400, "Missing questions file (.txt)")

        raw_questions = (await questions_file.read()).decode("utf-8")
        
        pickle_path = None
        df_preview = ""
        dataset_uploaded = False

        if data_file:
            dataset_uploaded = True
            filename = data_file.filename.lower()
            content = await data_file.read()
            from io import BytesIO
            import duckdb, tempfile, tarfile, zipfile

            df = None
            duckdb_conn = duckdb.connect(database=':memory:')

            # CSV
            if filename.endswith(".csv"):
                df = pd.read_csv(BytesIO(content))
                duckdb_conn.register("df", df)

            # Excel
            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(BytesIO(content))
                duckdb_conn.register("df", df)
            
            elif filename.lower().endswith(".pdf"):
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise HTTPException(500, "GOOGLE_API_KEY not set")
                genai.configure(api_key=api_key)

                # Send PDF bytes directly to Gemini
                parts = [
                    {
                        "mime_type": "application/pdf",
                        "data": content,  # raw PDF bytes
                    },
                    {
                        "text": (
                            "Extract ALL tabular data from the PDF as JSON only, format:\n"
                            '{"columns":["col1",...],"rows":[["r1c1",...],["r2c1",...]]}\n'
                            "If multiple tables, merge into one if columns match. "
                            "Keep numbers numeric; no commentary."
                        )
                    }
                ]

                model = genai.GenerativeModel("gemini-1.5-flash")
                resp = model.generate_content(parts)
                raw = (resp.text or "").strip()

                # Extract JSON
                m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
                payload = m.group(0) if m else ""

                try:
                    obj = json.loads(payload)
                    cols = obj.get("columns", [])
                    rows = obj.get("rows", [])
                    df = pd.DataFrame(rows, columns=cols if cols else None)
                    df = df.apply(pd.to_numeric, errors="ignore")
                    duckdb_conn.register("df", df)
                except Exception:
                    # Fallback: just get text
                    resp2 = model.generate_content([parts[0], {"text": "Extract all visible text. Return plain text only."}])
                    pdf_text = (resp2.text or "").strip()
                    df = pd.DataFrame({"ocr_text": [pdf_text]})
                    duckdb_conn.register("df", df)

            # Parquet
            elif filename.endswith(".parquet"):
                df = pd.read_parquet(BytesIO(content))
                duckdb_conn.register("df", df)

            # SQLite / DuckDB database
            elif filename.endswith(".db") or filename.endswith(".duckdb"):
                tmp_path = tempfile.NamedTemporaryFile(delete=False).name
                with open(tmp_path, "wb") as f:
                    f.write(content)
                duckdb_conn.execute(f"ATTACH '{tmp_path}' AS uploaded_db")
                # Pick the first table for df
                tables = duckdb_conn.execute("SHOW TABLES FROM uploaded_db").fetchdf()
                if not tables.empty:
                    first_table = tables.iloc[0, 0]
                    df = duckdb_conn.execute(f"SELECT * FROM uploaded_db.{first_table}").fetchdf()

            # Archives (.tar.gz, .zip)
            elif filename.endswith((".tar.gz", ".tgz", ".tar", ".zip")):
                content_io = BytesIO(content)
                if filename.endswith(".zip"):
                    with zipfile.ZipFile(content_io, 'r') as z:
                        for name in z.namelist():
                            if name.endswith(".parquet"):
                                df = pd.read_parquet(z.open(name))
                                break
                            if name.endswith(".csv"):
                                df = pd.read_csv(z.open(name))
                                break
                else:
                    with tarfile.open(fileobj=content_io, mode="r:*") as tar:
                        for member in tar.getmembers():
                            if member.name.endswith(".parquet"):
                                df = pd.read_parquet(tar.extractfile(member))
                                break
                            if member.name.endswith(".csv"):
                                df = pd.read_csv(tar.extractfile(member))
                                break
                if df is not None:
                    duckdb_conn.register("df", df)

            # JSON
            elif filename.endswith(".json"):
                try:
                    df = pd.read_json(BytesIO(content))
                except ValueError:
                    df = pd.DataFrame(json.loads(content.decode("utf-8")))
                duckdb_conn.register("df", df)

            elif filename.lower().endswith((".png", ".jpg", ".jpeg")):
                import io, os, json, re
                import google.generativeai as genai

                # 1) Configure Gemini
                api_key = os.getenv("GOOGLE_API_KEY")
                if not api_key:
                    raise HTTPException(500, "GOOGLE_API_KEY not set")
                genai.configure(api_key=api_key)

                # 2) Read image bytes
                image_bytes = content  # already read earlier
                # Build the multimodal input
                parts = [
                    {
                        "mime_type": (
                            "image/png" if filename.lower().endswith(".png")
                            else "image/jpeg"
                        ),
                        "data": image_bytes,
                    },
                    {
                        "text": (
                            "You are a table extractor. "
                            "From the provided image, extract ALL tabular data into a single JSON object "
                            "with the following shape ONLY:\n\n"
                            "{\n"
                            '  "columns": ["col1","col2",...],\n'
                            '  "rows": [ ["r1c1","r1c2",...], ["r2c1","r2c2",...], ... ]\n'
                            "}\n\n"
                            "Rules:\n"
                            "- Infer column names from the image header if present; otherwise use generic names like Col1, Col2, ...\n"
                            "- Keep numbers as numbers (no commas), text as strings.\n"
                            "- Do not add commentary. Return ONLY valid minified JSON."
                        )
                    }
                ]

                # 3) Call Gemini (no Tesseract needed)
                model = genai.GenerativeModel("gemini-1.5-flash")
                try:
                    resp = model.generate_content(parts)
                    raw = resp.text or ""
                except Exception as e:
                    raise HTTPException(500, f"Gemini error: {e}")

                # 4) Extract strict JSON
                #    (Sometimes models add accidental text; strip it and keep only the first JSON object.)
                def extract_json(s: str):
                    # find first {...} block
                    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
                    return m.group(0) if m else ""

                payload = extract_json(raw)

                # 5) Build DataFrame from JSON or fall back to raw text
                try:
                    obj = json.loads(payload)
                    cols = obj.get("columns", [])
                    rows = obj.get("rows", [])

                    if rows and isinstance(rows[0], dict):
                        df = pd.DataFrame(rows)
                        # ensure column order
                        if cols:
                            df = df[[c for c in cols if c in df.columns]]
                    else:
                        df = pd.DataFrame(rows, columns=cols if cols else None)

                    # Optional: coerce numeric-looking strings to numbers
                    df = df.apply(pd.to_numeric, errors="ignore")

                    duckdb_conn.register("df", df)

                except Exception:
                    # Fallback: ask Gemini for plain text and pass it to the model
                    # (works with your existing questions if they parse text first)
                    try:
                        model_text = genai.GenerativeModel("gemini-1.5-flash")
                        resp2 = model_text.generate_content([
                            parts[0],
                            {"text": "Extract all text content from the image. Return plain text only."}
                        ])
                        ocr_text = (resp2.text or "").strip()
                    except Exception:
                        ocr_text = ""

                    df = pd.DataFrame({"ocr_text": [ocr_text]})
                    duckdb_conn.register("df", df)


            else:
                raise HTTPException(400, f"Unsupported data file type: {filename}")

            # Save pickle for LLM code injection
            temp_pkl = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
            temp_pkl.close()
            df.to_pickle(temp_pkl.name)
            pickle_path = temp_pkl.name

            # Inject duckdb_conn into execution environment
            df_preview = (
                f"\n\nThe uploaded dataset has {len(df)} rows and {len(df.columns)} columns.\n"
                f"Columns: {', '.join(df.columns.astype(str))}\n"
                f"First rows:\n{df.head(5).to_markdown(index=False)}\n"
                f"You can also query the dataset using DuckDB via the variable `duckdb_conn`.\n"
            )

        # Build rules based on data presence
        if dataset_uploaded:
            llm_rules = (
                "Rules:\n"
                "1) You have access to a pandas DataFrame called `df` and its dictionary form `data`.\n"
                "2) DO NOT call scrape_url_to_dataframe() or fetch any external data.\n"
            )
        else:
            llm_rules = (
                "Rules:\n"
                "1) If you need web data, CALL scrape_url_to_dataframe(url).\n"
            )

        llm_input = (
            f"{llm_rules}\nQuestions:\n{raw_questions}\n"
            f"{df_preview if df_preview else ''}"
            "Respond with the JSON object only."
        )

        # Run agent
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as ex:
            fut = ex.submit(run_agent_safely_unified, llm_input, pickle_path)
            try:
                result = fut.result(timeout=LLM_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                raise HTTPException(408, "Processing timeout")

        if "error" in result:
            raise HTTPException(500, detail=result["error"])
        print(result)
        return JSONResponse(content=result)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("analyze_data failed")
        raise HTTPException(500, detail=str(e))


def run_agent_safely_unified(llm_input: str, pickle_path: str = None) -> Dict:
    """
    Runs the LLM agent and executes code.
    - Retries up to 3 times if agent returns no output.
    - If pickle_path is provided, injects that DataFrame directly.
    - If no pickle_path, falls back to scraping when needed.
    """
    try:
        max_retries = 5
        raw_out = ""
        for attempt in range(1, max_retries + 1):
            response = agent_executor.invoke({"input": llm_input}, {"timeout": LLM_TIMEOUT_SECONDS})
            raw_out = response.get("output") or response.get("final_output") or response.get("text") or ""
            if raw_out:
                break
        if not raw_out:
            return {"error": f"Agent returned no output after {max_retries} attempts"}

        parsed = clean_llm_output(raw_out)
        if "error" in parsed:
            return parsed

        if not isinstance(parsed, dict) or "code" not in parsed or ("questions" not in parsed and "keys" not in parsed):
            return {"error": f"Invalid agent response format: {parsed}"}



        code = parsed["code"]
        if pickle_path is None:
            urls = re.findall(r"scrape_url_to_dataframe\(\s*['\"](.*?)['\"]\s*\)", code)
            if urls:
                url = urls[0]
                tool_resp = scrape_url_to_dataframe(url)
                if tool_resp.get("status") != "success":
                    return {"error": f"Scrape tool failed: {tool_resp.get('message')}"}
                df = pd.DataFrame(tool_resp["data"])
                temp_pkl = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
                temp_pkl.close()
                df.to_pickle(temp_pkl.name)
                pickle_path = temp_pkl.name

        exec_result = write_and_run_temp_python(code, injected_pickle=pickle_path, timeout=LLM_TIMEOUT_SECONDS)
        if exec_result.get("status") != "success":
            return {"error": f"Execution failed: {exec_result.get('message')}", "raw": exec_result.get("raw")}

        results_dict = exec_result.get("result", {})
        return results_dict

    except Exception as e:
        logger.exception("run_agent_safely_unified failed")
        return {"error": str(e)}


    
from fastapi.responses import FileResponse, Response
import base64, os

# 1×1 transparent PNG fallback (if favicon.ico file not present)
_FAVICON_FALLBACK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3n+9QAAAAASUVORK5CYII="
)

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """
    Serve favicon.ico if present in the working directory.
    Otherwise return a tiny transparent PNG to avoid 404s.
    """
    path = "favicon.ico"
    if os.path.exists(path):
        return FileResponse(path, media_type="image/x-icon")
    return Response(content=_FAVICON_FALLBACK_PNG, media_type="image/png")

@app.get("/api", include_in_schema=False)
async def analyze_get_info():
    """Health/info endpoint. Use POST /api for actual analysis."""
    return JSONResponse({
        "ok": True,
        "message": "Server is running. Use POST /api with 'questions_file' and optional 'data_file'.",

    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))