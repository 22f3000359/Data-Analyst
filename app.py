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
from io import BytesIO, StringIO
from typing import Dict, Any, List
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi import FastAPI, Request
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

# LangChain / LLM imports (keep as you used)
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TDS Data Analyst Agent")

LLM_TIMEOUT_SECONDS = 180


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main HTML interface"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found</h1><p>Please ensure index.html is in the same directory as app.py</p>", status_code=404)


def parse_keys_and_types(raw_questions: str):
    """
    Parses the key/type section from the questions file.
    Returns:
        keys_list: list of keys in order
        type_map: dict key -> casting function
    """
    import re
    pattern = r"-\s*`([^`]+)`\s*:\s*(\w+)"
    matches = re.findall(pattern, raw_questions)
    type_map_def = {
        "number": float,
        "string": str,
        "integer": int,
        "int": int,
        "float": float
    }
    type_map = {key: type_map_def.get(t.lower(), str) for key, t in matches}
    keys_list = [k for k, _ in matches]
    return keys_list, type_map


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
from io import StringIO

def scrape_url_to_dataframe(url: str) -> Dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
        "Referer": "https://www.google.com"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        try:
            tables = pd.read_html(StringIO(resp.text))
            if tables:
                df = tables[0]
                df.columns = [str(c).strip() for c in df.columns]
                return {
                    "status": "success",
                    "data": df.to_dict(orient="records"),
                    "columns": list(df.columns)
                }
        except Exception:
            pass
    except Exception:
        pass

    # --- Fallback: use Playwright if direct request fails (e.g., 403) ---
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=45000)
            page.wait_for_load_state("networkidle")
            html = page.content()
            browser.close()

        tables = pd.read_html(StringIO(html))
        if tables:
            df = tables[0]
            df.columns = [str(c).strip() for c in df.columns]
            return {
                "status": "success",
                "data": df.to_dict(orient="records"),
                "columns": list(df.columns)
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Scraping failed (requests+playwright): {str(e)}",
            "data": [],
            "columns": []
        }

    return {"status": "error", "message": "No tables found", "data": [], "columns": []}
'''
def normalize_strptime(sql: str) -> str:
    # Pattern to find strptime with any first argument
    pattern = r"strptime\s*\(\s*([^,]+?)\s*,\s*['\"].*?['\"]\s*\)"
    
    # Replacement function to wrap the first argument in a CAST to VARCHAR
    def cast_arg(match):
        arg = match.group(1).strip()
        # Only cast if it's a column name (not a string literal or function call)
        if not (arg.startswith("'") or arg.startswith('"') or '(' in arg):
            return f"strptime(CAST({arg} AS VARCHAR), "
        return match.group(0)

    # Use re.sub with a replacement function
    sql = re.sub(r'strptime\s*\(\s*([^,]+?)\s*,', cast_arg, sql, flags=re.IGNORECASE)
    


def write_and_run_temp_python(code: str, injected_pickle: str = None, timeout: int = 60) -> Dict[str, Any]:
    """
    Write a temp python file which:
      - provides a safe environment (imports)
      - loads df/from pickle if provided into df and data variables
      - defines a robust plot_to_base64() helper that ensures < 95kB (attempts resizing/conversion)
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
    preamble.append("import duckdb, re")
    preamble.append(r'''
def normalize_strptime(sql: str) -> str:
    # Pattern to find strptime with any first argument
    pattern = r"strptime\\s*\\(\\s*([^,]+?)\\s*,"
    
    # Replacement function to wrap the first argument in a CAST to VARCHAR
    def cast_arg(match):
        arg = match.group(1).strip()
        # Only cast if it's a column name (not a string literal or function call)
        if not (arg.startswith("'") or arg.startswith('"') or '(' in arg):
            return f"strptime(CAST({arg} AS VARCHAR), "
        return match.group(0)

    # Use re.sub with a replacement function
    sql = re.sub(r"strptime\s*\(\s*([^,]+?)\s*,", cast_arg, sql, flags=re.IGNORECASE)


    return sql

class SafeDuckDB:
    def __init__(self, conn):
        self._conn = conn
    def execute(self, sql: str):
        sql = normalize_strptime(sql)
        return self._conn.execute(sql)

duckdb_conn = SafeDuckDB(duckdb.connect(database=':memory:'))
''')
    if PIL_AVAILABLE:
        preamble.append("from PIL import Image")
    # inject df if a pickle path provided
    if injected_pickle:
        preamble.append(f"df = pd.read_pickle(r'''{injected_pickle}''')\n")
        preamble.append("data = df.to_dict(orient='records')\n")
    else:
        # ensure data exists so user code that references data won't break
        preamble.append("data = globals().get('data', {})\n")
    # Ensure df and dfs aliases always exist
    preamble.append('''
# Normalise aliases for robustness
try:
    import pandas as pd
except ImportError:
    pass

# Ensure df exists if possible
if "df" not in globals() and "data" in globals() and isinstance(data, list):
    try:
        df = pd.DataFrame(data)
    except Exception:
        df = None

# Ensure dfs alias always exists
if "df" in globals() and df is not None:
    dfs = [df]
else:
    try:
        dfs = [pd.DataFrame(data)] if "data" in globals() and isinstance(data, list) else []
    except Exception:
        dfs = []

# Ensure scraped_data alias exists
if "df" in globals() and df is not None:
    scraped_data = {
        "status": "success",
        "data": df.to_dict(orient="records"),
        "as_dataframe": df
    }
elif "data" in globals() and isinstance(data, list):
    try:
        scraped_data = {
            "status": "success",
            "data": data,
            "as_dataframe": pd.DataFrame(data) if len(data) > 0 else pd.DataFrame()
        }
    except Exception:
        scraped_data = {"status": "success", "data": data}
else:
    scraped_data = {"status": "error", "data": []}

''')

    # plot_to_base64 helper that tries to reduce size under 100_000 bytes
    helper = r'''
    def plot_to_base64(max_bytes=95000):
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
        except Exception:
            pass


# -----------------------------
# LLM agent setup
# -----------------------------
llm = ChatGoogleGenerativeAI(
    model= "gemini-2.5-pro",
    temperature=0,
    google_api_key=os.getenv("GOOGLE_API_KEY")
)

# Tools list for agent (LangChain tool decorator returns metadata for the LLM)
tools = [scrape_url_to_dataframe]  # we only expose scraping as a tool; agent will still produce code

# Prompt: instruct agent to call the tool and output JSON only
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a full-stack autonomous data analyst agent.

You will receive:
- A set of **rules** for this request (these rules may differ depending on whether a dataset is uploaded or not)
- One or more **questions**
- An optional **dataset preview**

You must:
1. Follow the provided rules exactly.
2. Return only a valid JSON object — no extra commentary or formatting.
3. The JSON must contain:
   - "questions": [ list of original question strings exactly as provided ]
   - "code": "..." (Python code that creates a dict called `results` with each question string as a key and its computed answer as the value)
4. Your Python code will run in a sandbox with:
   - pandas, numpy, matplotlib available
   - A helper function `plot_to_base64(max_bytes=100000)` for generating base64-encoded images under 100KB.
5. When returning plots, always use `plot_to_base64()` to keep image sizes small.
6. Make sure all variables are defined before use, and the code can run without any undefined references.
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

@app.post("/api/")
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
        keys_list, type_map = parse_keys_and_types(raw_questions)

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

            # Handle CSV
            if filename.endswith(".csv"):
                df = pd.read_csv(BytesIO(content))
                duckdb_conn.register("df", df)

            # Handle Excel
            elif filename.endswith((".xlsx", ".xls")):
                df = pd.read_excel(BytesIO(content))
                duckdb_conn.register("df", df)

            # Handle Parquet
            elif filename.endswith(".parquet"):
                df = pd.read_parquet(BytesIO(content))
                duckdb_conn.register("df", df)

            # Handle SQLite / DuckDB
            elif filename.endswith(".db") or filename.endswith(".duckdb"):
                tmp_path = tempfile.NamedTemporaryFile(delete=False).name
                with open(tmp_path, "wb") as f:
                    f.write(content)
                duckdb_conn.execute(f"ATTACH '{tmp_path}' AS uploaded_db")
                tables = duckdb_conn.execute("SHOW TABLES FROM uploaded_db").fetchdf()
                if not tables.empty:
                    first_table = tables.iloc[0, 0]
                    df = duckdb_conn.execute(f"SELECT * FROM uploaded_db.{first_table}").fetchdf()

            # Handle archives
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

            # Handle JSON
            elif filename.endswith(".json"):
                try:
                    df = pd.read_json(BytesIO(content))
                except ValueError:
                    df = pd.DataFrame(json.loads(content.decode("utf-8")))
                duckdb_conn.register("df", df)

            # Handle images
            elif filename.endswith((".png", ".jpg", ".jpeg")):
                if PIL_AVAILABLE:
                    image = Image.open(BytesIO(content)).convert("RGB")
                    df = pd.DataFrame({"image": [image]})
                    duckdb_conn.register("df", df)
                else:
                    raise HTTPException(400, "PIL not available for image processing")

            # Handle PDFs
            elif filename.endswith(".pdf"):
                from PyPDF2 import PdfReader
                reader = PdfReader(BytesIO(content))
                text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
                df = pd.DataFrame({"text": [text]})
                duckdb_conn.register("df", df)

            else:
                raise HTTPException(400, f"Unsupported data file type: {filename}")

            # Save pickle for LLM code injection
            temp_pkl = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
            temp_pkl.close()
            df.to_pickle(temp_pkl.name)
            pickle_path = temp_pkl.name

            df_preview = (
                f"\n\nThe uploaded dataset has {len(df)} rows and {len(df.columns)} columns.\n"
                f"Columns: {', '.join(df.columns.astype(str))}\n"
                f"First rows:\n{df.head(5).to_markdown(index=False)}\n"
                f"You can also query the dataset using DuckDB via the variable `duckdb_conn`.\n"
            )

        # Build LLM rules
        if dataset_uploaded:
            llm_rules = (
                "Rules:\n"
                "1) You have access to a pandas DataFrame called `df` and its dictionary form `data`.\n"
                "2) DO NOT call scrape_url_to_dataframe() or fetch any external data.\n"
                "3) Use only the uploaded dataset for answering questions.\n"
                "4) Produce a final JSON object with keys:\n"
                '   - "questions": [ ... original question strings ... ]\n'
                '   - "code": "..."  (Python code that fills `results` with exact question strings as keys)\n'
                "5) For plots: use plot_to_base64() helper to return base64 image data under 95kB.\n"
            )
        else:
            llm_rules = (
                "Rules:\n"
                "1) If you need web data, CALL scrape_url_to_dataframe(url).\n"
                "2) Produce a final JSON object with keys:\n"
                '   - "questions": [ ... original question strings ... ]\n'
                '   - "code": "..."  (Python code that fills `results` with exact question strings as keys)\n'
                "3) For plots: use plot_to_base64() helper to return base64 image data under 95kB.\n"
            )

        llm_input = (
            f"{llm_rules}\nQuestions:\n{raw_questions}\n"
            f"{df_preview if df_preview else ''}"
            "Respond with the JSON object only."
        )

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as ex:
            fut = ex.submit(run_agent_safely_unified, llm_input, pickle_path, keys_list, type_map)
            try:
                result = fut.result(timeout=LLM_TIMEOUT_SECONDS)
            except concurrent.futures.TimeoutError:
                raise HTTPException(408, "Processing timeout")

        if "error" in result:
            logger.error(f"Analysis failed: {result['error']}")
            if keys_list:
                return JSONResponse({k: "can't find answer" for k in keys_list})
            else:
                return JSONResponse({"result": "can't find answer"})

        return JSONResponse(content=result)

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("analyze_data failed")
        raise HTTPException(500, detail=str(e))


def run_agent_safely_unified(
    llm_input: str,
    pickle_path: str = None,
    keys_list=None,
    type_map=None
) -> Dict:
    """
    Runs the LLM agent and executes code, with a retry loop for execution errors.
    - If keys_list is provided and any of its keys are in the result, map to that structure.
    - Otherwise, return the result as is.
    """

    injected_pickle_path = None
    try:
        max_retries_total = 4
        raw_out = ""
        last_error = None
        current_llm_input = llm_input

        for attempt in range(1, max_retries_total + 1):
            # Step 1: Get code from agent
            response = agent_executor.invoke({"input": current_llm_input})
            raw_out = (
                response.get("output")
                or response.get("final_output")
                or response.get("text")
                or ""
            )
            if not raw_out:
                last_error = f"Agent returned no output after {attempt} attempts"
                continue

            parsed = clean_llm_output(raw_out)
            if "error" in parsed:
                last_error = f"JSON parsing failed: {parsed['error']}"
                continue
            if "code" not in parsed:
                last_error = f"Invalid agent response: No 'code' key in {parsed}"
                continue

            code = parsed["code"]

            # Step 2: Handle data injection (if necessary)
            if not pickle_path:  # only scrape/inject if no file was provided
                urls = re.findall(r"scrape_url_to_dataframe\(\s*['\"](.*?)['\"]\s*\)", code)
                if urls:
                    url = urls[0]
                    tool_resp = scrape_url_to_dataframe(url)
                    if tool_resp.get("status") != "success":
                        last_error = f"Scrape tool failed: {tool_resp.get('message')}"
                        continue
                    df = pd.DataFrame(tool_resp["data"])
                    temp_pkl = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
                    temp_pkl.close()
                    df.to_pickle(temp_pkl.name)
                    injected_pickle_path = temp_pkl.name
            else:
                injected_pickle_path = pickle_path

            # Step 3: Execute the generated code
            exec_result = write_and_run_temp_python(
                code, injected_pickle=injected_pickle_path, timeout=LLM_TIMEOUT_SECONDS
            )

                    
            def strip_data_uri_prefix(val):
                """Remove data:image/...;base64, prefix from any base64 string"""
                if isinstance(val, str):
                    return re.sub(r'^data:image/[a-zA-Z0-9.+-]+;base64,', '', val)
                return val

            if exec_result.get("status") == "success":
                raw_results = exec_result.get("result", {})
                results_dict = {k: strip_data_uri_prefix(v) for k, v in raw_results.items()}
                if keys_list and type_map:
                    mapped = {}
                    questions = parsed.get("questions", [])
                    for idx, question in enumerate(questions):
                        if idx < len(keys_list):
                            key = keys_list[idx]
                            caster = type_map.get(key, str)
                            val = results_dict.get(question)
                            try:
                                mapped[key] = (
                                    caster(val) if val not in (None, "") else val
                                )
                            except Exception:
                                mapped[key] = val
                    return mapped
                return results_dict
            else:
                # Step 4: Execution failed. Retry with error feedback
                last_error = f"Execution failed: {exec_result.get('message')}"
                current_llm_input = (
                    f"Previous attempt's Python code failed with the following error:\n"
                    f"---CODE START---\n{code}\n---CODE END---\n"
                    f"---ERROR START---\n{exec_result.get('message')}\n---ERROR END---\n"
                    f"Please generate a new, corrected Python code to answer the questions."
                )
  # If we reach here → all retries failed
        logger.error(f"Final failure after retries: {last_error}")
        if keys_list:
            return {k: "can't find answer" for k in keys_list}
        else:
            return {"result": "can't find answer"}

    except Exception as e:
        logger.exception("run_agent_safely_unified failed")
        if keys_list:
            return {k: "can't find answer" for k in keys_list}
        else:
            return {"result": "can't find answer"}

    finally:
        for p in {pickle_path, injected_pickle_path}:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except Exception:
                    pass
                
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

