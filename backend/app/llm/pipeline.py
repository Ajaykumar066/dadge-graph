"""
pipeline.py

LangChain + Gemini pipeline for natural language → Cypher → answer.

FLOW:
1. Guardrail check — reject off-topic questions immediately
2. Generate Cypher — LLM translates NL question into Cypher
3. Execute Cypher — run against Neo4j, get raw rows
4. Generate answer — LLM summarizes rows into natural language
5. Extract node IDs — so frontend can highlight referenced nodes

WHY TWO LLM CALLS (generate + summarize):
Separating concerns makes each prompt simpler and more reliable.
The first LLM call only needs to think about Cypher syntax.
The second only needs to think about explaining data clearly.
One combined prompt tries to do both and does neither well.
"""

import json
import logging
import re
from typing import Optional

from groq import Groq
from google import genai
from google.genai import types

from app.core.config import get_settings
from app.core.database import get_driver

LLM_MODEL = "llama-3.3-70b-versatile"

logger = logging.getLogger(__name__)

# ── Graph schema fed to the LLM ──────────────────────────────────────────────
# This is the single most important prompt engineering decision.
# The LLM cannot generate correct Cypher without knowing:
# - exact node labels
# - exact property names
# - exact relationship types
# WHY CONCISE: Gemini Flash has a large context window but shorter,
# precise schemas produce better Cypher than exhaustive ones.

GRAPH_SCHEMA = """
NODES and their key properties:
- BusinessPartner:   businessPartner (ID), fullName, country, city, isBlocked
- SalesOrder:        salesOrder (ID), soldToParty→BP, totalNetAmount, transactionCurrency, overallDeliveryStatus, creationDate
- SalesOrderItem:    itemId (ID), salesOrder→SO, material→Product, requestedQuantity, netAmount
- SalesOrderScheduleLine: scheduleId (ID), salesOrder, confirmedDeliveryDate, confdOrderQtyByMatlAvailCheck
- OutboundDelivery:  deliveryDocument (ID), overallGoodsMovementStatus, overallPickingStatus, actualGoodsMovementDate
- OutboundDeliveryItem: deliveryItemId (ID), deliveryDocument→OD, referenceSdDocument→SO, plant→Plant
- BillingDocument:   billingDocument (ID), soldToParty→BP, totalNetAmount, billingDocumentDate, billingDocumentIsCancelled
- BillingDocumentItem: billingItemId (ID), billingDocument→BD, referenceSdDocument→OD, material→Product, netAmount
- JournalEntry:      journalEntryId (ID), accountingDocument, referenceDocument→BD, customer→BP, amountInTransactionCurrency, postingDate
- Payment:           paymentId (ID), clearingAccountingDocument, accountingDocument→JE, customer→BP, amountInTransactionCurrency, clearingDate
- Product:           product (ID), description, productType, productGroup
- Plant:             plant (ID), plantName, salesOrganization

RELATIONSHIPS (directionality matters in Cypher):
(BusinessPartner)-[:PLACED]->(SalesOrder)
(SalesOrder)-[:HAS_ITEM]->(SalesOrderItem)
(SalesOrder)-[:HAS_SCHEDULE_LINE]->(SalesOrderScheduleLine)
(SalesOrder)-[:FULFILLED_BY]->(OutboundDelivery)
(SalesOrderItem)-[:FOR_PRODUCT]->(Product)
(OutboundDelivery)-[:HAS_ITEM]->(OutboundDeliveryItem)
(OutboundDeliveryItem)-[:SHIPPED_FROM]->(Plant)
(OutboundDelivery)-[:BILLED_AS]->(BillingDocument)
(BillingDocument)-[:HAS_ITEM]->(BillingDocumentItem)
(BillingDocumentItem)-[:FOR_PRODUCT]->(Product)
(BillingDocument)-[:BILLED_TO]->(BusinessPartner)
(BillingDocument)-[:RECORDED_IN]->(JournalEntry)
(JournalEntry)-[:CLEARED_BY]->(Payment)
(Product)-[:AVAILABLE_AT]->(Plant)
"""

# ── Guardrail keywords ────────────────────────────────────────────────────────
# Questions must relate to at least one of these domain concepts.
# Phrases that are clearly off-topic — checked FIRST
OFF_TOPIC_PATTERNS = [
    "poem", "song", "story", "joke", "write me", "tell me a",
    "capital of", "weather", "recipe", "translate", "who is",
    "what is the meaning", "history of", "explain quantum",
]

# Domain keywords — must match AFTER off-topic check passes
DOMAIN_KEYWORDS = [
    "sales order", "delivery", "billing", "invoice", "payment",
    "journal", "product", "customer", "plant", "material",
    "order", "shipment", "dispatch", "amount", "quantity",
    "status", "flow", "o2c", "sap", "partner", "document",
    "entry", "account", "cleared", "billed", "fulfilled",
    "shipped", "cancelled", "revenue", "billing document",
    "outbound", "schedule line", "business partner",
]


def _is_domain_question(question: str) -> bool:
    """
    Returns True only if the question is about SAP O2C data.

    Layer 1: Reject obvious off-topic patterns immediately.
    Layer 2: Require at least one domain keyword to be present.
    """
    q_lower = question.lower()

    # Layer 1 — reject off-topic patterns first
    if any(pattern in q_lower for pattern in OFF_TOPIC_PATTERNS):
        return False

    # Layer 2 — must contain at least one domain keyword
    return any(kw in q_lower for kw in DOMAIN_KEYWORDS)



def _clean_cypher(raw: str) -> str:
    """
    Strips markdown fences and whitespace from LLM-generated Cypher.

    LLMs often wrap code in ```cypher ... ``` blocks.
    Neo4j driver rejects these — we must strip them first.
    """
    # Remove ```cypher ... ``` or ``` ... ```
    raw = re.sub(r"```(?:cypher)?", "", raw, flags=re.IGNORECASE)
    raw = raw.replace("```", "")
    return raw.strip()


def _get_llm_client() -> Groq:
    """Returns a configured Groq client."""
    settings = get_settings()
    return Groq(api_key=settings.groq_api_key)

# Replace generate_cypher() with this:
def generate_cypher(question: str) -> str:
    """
    Calls Groq/Llama to translate natural language into Cypher.
    """
    client = _get_llm_client()

    system_prompt = f"""You are a Neo4j Cypher expert for a SAP Order-to-Cash graph database.

SCHEMA:
{GRAPH_SCHEMA}

RULES:
- Return ONLY valid Cypher. No explanation, no markdown, no comments.
- Always add LIMIT 50 unless the question asks for counts/aggregations.
- Use case-insensitive matching: toLower(n.field) CONTAINS toLower('value')
- For "full flow" or "trace" questions, use MATCH with a path pattern.
- For "broken flow" questions, use WHERE NOT (n)-[:REL]->() pattern.
- Never use APOC procedures.
- Property names are camelCase — match the schema exactly.

EXAMPLES:
Q: Which products have the most billing documents?
A: MATCH (bdi:BillingDocumentItem)-[:FOR_PRODUCT]->(p:Product)
   RETURN p.description AS product, count(bdi) AS billingCount
   ORDER BY billingCount DESC LIMIT 10

Q: Trace the full flow of billing document 90504248
A: MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
   -[:BILLED_AS]->(bd:BillingDocument {{billingDocument: '90504248'}})
   -[:RECORDED_IN]->(je:JournalEntry)-[:CLEARED_BY]->(pay:Payment)
   RETURN so.salesOrder, od.deliveryDocument,
          bd.billingDocument, je.accountingDocument,
          pay.clearingAccountingDocument

Q: Find orders delivered but not billed
A: MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
   WHERE NOT (od)-[:BILLED_AS]->()
   RETURN so.salesOrder, od.deliveryDocument,
          od.actualGoodsMovementDate LIMIT 50"""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": f"Q: {question}\nA:"},
        ],
        temperature=0.0,
        max_tokens=512,
    )

    raw_cypher = response.choices[0].message.content or ""
    return _clean_cypher(raw_cypher)

def execute_cypher(cypher: str) -> list[dict]:
    """
    Executes a Cypher query against Neo4j.
    Returns rows as a list of plain dicts.

    WHY SERIALIZE MANUALLY:
    Neo4j records contain Node/Relationship objects that are not
    JSON-serializable. We convert everything to strings/dicts.
    """
    driver = get_driver()

    with driver.session() as session:
        result = session.run(cypher)
        rows = []
        for record in result:
            row = {}
            for key in record.keys():
                value = record[key]
                # Node object → extract properties dict
                if hasattr(value, "labels"):
                    row[key] = {
                        "id":         str(value.element_id),
                        "labels":     list(value.labels),
                        "properties": dict(value),
                    }
                # Relationship object → extract type + endpoints
                elif hasattr(value, "type"):
                    row[key] = {
                        "type":      value.type,
                        "startNode": str(value.start_node.element_id),
                        "endNode":   str(value.end_node.element_id),
                    }
                # Path object → serialize as string
                elif hasattr(value, "nodes"):
                    row[key] = str(value)
                else:
                    row[key] = value
            rows.append(row)
        return rows

def generate_answer(question: str, cypher: str, rows: list[dict]) -> str:
    """
    Calls Groq/Llama to summarize query results into natural language.
    """
    client = _get_llm_client()

    display_rows = rows[:20]
    rows_json = json.dumps(display_rows, indent=2, default=str)

    if not rows:
        data_section = "The query returned no results."
    else:
        data_section = f"""Query returned {len(rows)} result(s).
Showing first {len(display_rows)}:
{rows_json}"""

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful SAP Order-to-Cash business analyst. "
                    "Answer questions clearly using only the data provided. "
                    "Do NOT mention Cypher, Neo4j, or technical details. "
                    "Keep answers under 150 words. Use plain business language."
                ),
            },
            {
                "role": "user",
                "content": (
                    f'The user asked: "{question}"\n\n'
                    f"Cypher used:\n{cypher}\n\n"
                    f"{data_section}"
                ),
            },
        ],
        temperature=0.3,
        max_tokens=300,
    )

    return response.choices[0].message.content or "Could not generate an answer."


def extract_node_ids(rows: list[dict]) -> list[str]:
    """
    Extracts Neo4j element IDs from query results.
    Handles both node objects AND scalar ID values.
    """
    ids = []
    
    for row in rows:
        for key, value in row.items():
            # Case 1: value is a node object with element_id
            if isinstance(value, dict) and "id" in value:
                ids.append(value["id"])
            # Case 2: value looks like a SAP document ID (string/number)
            elif isinstance(value, (str, int)) and value:
                found = _lookup_node_id(str(value))
                if found:
                    ids.extend(found)

    return list(set(ids))


def _lookup_node_id(value: str) -> list[str]:
    """
    Given a SAP document value (e.g. '90504248', 'SUNSCREEN GEL...'),
    searches Neo4j for matching nodes and returns their element IDs.
    """
    if not value or len(value) < 3:
        return []

    driver = get_driver()
    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE n.billingDocument      = $val
                   OR n.salesOrder           = $val
                   OR n.deliveryDocument     = $val
                   OR n.product              = $val
                   OR n.description          = $val
                   OR n.businessPartner      = $val
                   OR n.accountingDocument   = $val
                   OR n.paymentId            = $val
                RETURN elementId(n) AS eid
                LIMIT 5
                """,
                {"val": value}
            )
            return [r["eid"] for r in result]
    except Exception:
        return []

def run_query(question: str) -> dict:
    """
    Main entry point: NL question → Cypher → answer.

    FLOW:
    1. Guardrail check — reject off-topic questions immediately
    2. Generate Cypher — LLM translates NL question into Cypher
    3. Execute Cypher — run against Neo4j, get raw rows
    4. Generate answer — LLM summarizes rows into natural language
    5. Extract node IDs — so frontend can highlight referenced nodes
    """

    # ── Guardrail ─────────────────────────────────────────────
    if not _is_domain_question(question):
        return {
            "answer": (
                "I can only answer questions about SAP Order-to-Cash data, "
                "such as sales orders, deliveries, billing documents, payments, "
                "products, and business partners."
            ),
            "cypher":            "",
            "rows":              [],
            "highlighted_nodes": [],
            "is_domain":         False,
        }

    # ── Generate Cypher ───────────────────────────────────────
    logger.info(f"Generating Cypher for: {question}")
    cypher = generate_cypher(question)
    logger.info(f"Generated Cypher:\n{cypher}")

    # ── Execute ───────────────────────────────────────────────
    try:
        rows = execute_cypher(cypher)
        logger.info(f"Query returned {len(rows)} rows")
    except Exception as e:
        import traceback
        logger.error(f"Cypher execution failed: {e}")
        logger.error(traceback.format_exc())
        return {
            "answer": (
                "I understood your question and generated a query, "
                "but it encountered an error during execution. "
                "Please try rephrasing your question."
            ),
            "cypher":            cypher,
            "rows":              [],
            "highlighted_nodes": [],
            "is_domain":         True,
            "error":             str(e),
        }

    # ── Summarize ─────────────────────────────────────────────
    answer = generate_answer(question, cypher, rows)
    highlighted = extract_node_ids(rows)

    return {
        "answer":            answer,
        "cypher":            cypher,
        "rows":              rows[:20],   # cap at 20 for response size
        "highlighted_nodes": highlighted,
        "is_domain":         True,
    }