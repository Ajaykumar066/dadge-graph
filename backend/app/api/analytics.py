"""
analytics.py

Pre-built analytical endpoints for the most important O2C queries.

WHY DEDICATED ENDPOINTS IN ADDITION TO THE CHAT:
The chat endpoint handles free-form NL questions but has LLM latency
(1-2 seconds per call). For these specific, high-value queries that
users will run frequently, we provide direct Cypher endpoints that
return in milliseconds — no LLM call needed.

These also serve as the "example queries" the frontend can expose
as quick-action buttons.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_driver

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _run_cypher(cypher: str, params: dict = None) -> list[dict]:
    """Executes a Cypher query and returns plain serializable rows."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run(cypher, params or {})
        rows = []
        for record in result:
            row = {}
            for key in record.keys():
                value = record[key]
                if hasattr(value, "labels"):
                    row[key] = {
                        "id":         str(value.element_id),
                        "labels":     list(value.labels),
                        "properties": dict(value),
                    }
                elif hasattr(value, "type"):
                    row[key] = {
                        "type":      value.type,
                        "startNode": str(value.start_node.element_id),
                        "endNode":   str(value.end_node.element_id),
                    }
                else:
                    row[key] = value
            rows.append(row)
        return rows


# ── Route 1: Full O2C Flow Trace ──────────────────────────────────────────────

@router.get("/flow-trace/{billing_document_id}")
async def trace_flow(billing_document_id: str):
    """
    Traces the complete Order-to-Cash flow for a given billing document.

    Returns every step in the chain:
    SalesOrder → OutboundDelivery → BillingDocument → JournalEntry → Payment

    WHY THIS IS VALUABLE:
    Auditors and business analysts need to trace a single transaction
    end-to-end to verify it completed correctly. This replaces what
    would otherwise be 5 separate database queries across 5 tables.

    Example: GET /api/analytics/flow-trace/90504248
    """
    try:
        # Step 1: Get the billing document + its sales order chain
        chain_rows = _run_cypher(
            """
            MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
                  -[:BILLED_AS]->(bd:BillingDocument {billingDocument: $bd_id})
            RETURN so.salesOrder            AS salesOrder,
                   so.soldToParty           AS customer,
                   so.totalNetAmount        AS orderAmount,
                   so.transactionCurrency   AS currency,
                   so.creationDate          AS orderDate,
                   so.overallDeliveryStatus AS deliveryStatus,
                   od.deliveryDocument      AS deliveryDocument,
                   od.actualGoodsMovementDate AS deliveryDate,
                   od.overallGoodsMovementStatus AS goodsMovementStatus,
                   bd.billingDocument       AS billingDocument,
                   bd.billingDocumentDate   AS billingDate,
                   bd.totalNetAmount        AS billingAmount,
                   bd.billingDocumentIsCancelled AS isCancelled
            """,
            {"bd_id": billing_document_id}
        )

        if not chain_rows:
            raise HTTPException(
                status_code=404,
                detail=f"Billing document '{billing_document_id}' not found "
                       f"or not linked to a sales order and delivery."
            )

        chain = chain_rows[0]

        # Step 2: Get journal entry for this billing document
        journal_rows = _run_cypher(
            """
            MATCH (bd:BillingDocument {billingDocument: $bd_id})
                  -[:RECORDED_IN]->(je:JournalEntry)
            RETURN je.accountingDocument          AS accountingDocument,
                   je.journalEntryId              AS journalEntryId,
                   je.amountInTransactionCurrency AS amount,
                   je.postingDate                 AS postingDate,
                   je.glAccount                   AS glAccount,
                   je.clearingAccountingDocument  AS clearingDocument
            """,
            {"bd_id": billing_document_id}
        )

        # Step 3: Get payment if journal entry exists
        payment_rows = []
        if journal_rows:
            clearing_doc = journal_rows[0].get("clearingDocument")
            if clearing_doc:
                payment_rows = _run_cypher(
                    """
                    MATCH (pay:Payment {clearingAccountingDocument: $clearing_doc})
                    RETURN pay.clearingAccountingDocument AS paymentDocument,
                           pay.clearingDate              AS paymentDate,
                           pay.amountInTransactionCurrency AS amount,
                           pay.transactionCurrency       AS currency
                    LIMIT 1
                    """,
                    {"clearing_doc": clearing_doc}
                )

        # Step 4: Get billing document items
        items_rows = _run_cypher(
            """
            MATCH (bd:BillingDocument {billingDocument: $bd_id})
                  -[:HAS_ITEM]->(bdi:BillingDocumentItem)
                  -[:FOR_PRODUCT]->(p:Product)
            RETURN bdi.billingDocumentItem AS itemNumber,
                   p.description          AS productDescription,
                   p.product              AS productId,
                   bdi.billingQuantity    AS quantity,
                   bdi.billingQuantityUnit AS unit,
                   bdi.netAmount          AS netAmount
            """,
            {"bd_id": billing_document_id}
        )

        # Determine flow completeness
        flow_status = _determine_flow_status(chain, journal_rows, payment_rows)

        return {
            "billingDocument": billing_document_id,
            "flowStatus":      flow_status,
            "chain": {
                "salesOrder":    {
                    "id":             chain.get("salesOrder"),
                    "customer":       chain.get("customer"),
                    "amount":         chain.get("orderAmount"),
                    "currency":       chain.get("currency"),
                    "date":           chain.get("orderDate"),
                    "deliveryStatus": chain.get("deliveryStatus"),
                },
                "delivery": {
                    "id":                  chain.get("deliveryDocument"),
                    "date":                chain.get("deliveryDate"),
                    "goodsMovementStatus": chain.get("goodsMovementStatus"),
                },
                "billing": {
                    "id":          chain.get("billingDocument"),
                    "date":        chain.get("billingDate"),
                    "amount":      chain.get("billingAmount"),
                    "isCancelled": chain.get("isCancelled"),
                },
                "journalEntry": journal_rows[0] if journal_rows else None,
                "payment":      payment_rows[0] if payment_rows else None,
            },
            "items": items_rows,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Flow trace error for {billing_document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _determine_flow_status(chain: dict, journal_rows: list, payment_rows: list) -> str:
    """
    Returns a human-readable status describing how complete this O2C flow is.
    Used by the frontend to show a status badge on the flow trace.
    """
    if chain.get("isCancelled"):
        return "CANCELLED"
    if payment_rows:
        return "COMPLETE"
    if journal_rows:
        return "BILLED_PENDING_PAYMENT"
    if chain.get("billingDocument"):
        return "BILLED_NO_JOURNAL"
    if chain.get("deliveryDocument"):
        return "DELIVERED_NOT_BILLED"
    return "IN_PROGRESS"


# ── Route 2: Broken Flow Detection ───────────────────────────────────────────

@router.get("/broken-flows")
async def get_broken_flows(
    flow_type: str = Query(
        default="all",
        description="Filter: all | no_delivery | no_billing | no_payment | cancelled"
    )
):
    """
    Identifies sales orders with incomplete or broken O2C flows.

    Flow types:
    - no_delivery:  Orders created but never fulfilled
    - no_billing:   Deliveries completed but never invoiced
    - no_payment:   Invoices created but never paid
    - cancelled:    Billing documents that were cancelled

    WHY THIS MATTERS:
    Broken flows represent revenue leakage. An order delivered but
    never billed means the company did the work but won't get paid.
    This endpoint surfaces those gaps instantly.
    """
    try:
        results = {}

        if flow_type in ("all", "no_delivery"):
            rows = _run_cypher(
                """
                MATCH (so:SalesOrder)
                WHERE NOT (so)-[:FULFILLED_BY]->()
                RETURN so.salesOrder          AS salesOrder,
                       so.soldToParty         AS customer,
                       so.totalNetAmount      AS amount,
                       so.transactionCurrency AS currency,
                       so.creationDate        AS creationDate,
                       so.overallDeliveryStatus AS deliveryStatus
                ORDER BY so.creationDate DESC
                LIMIT 50
                """
            )
            results["no_delivery"] = {
                "label":       "Orders with no delivery",
                "count":       len(rows),
                "description": "Sales orders that were created but never fulfilled with an outbound delivery.",
                "rows":        rows,
            }

        if flow_type in ("all", "no_billing"):
            rows = _run_cypher(
                """
                MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
                WHERE NOT (od)-[:BILLED_AS]->()
                RETURN so.salesOrder              AS salesOrder,
                       so.soldToParty             AS customer,
                       od.deliveryDocument        AS deliveryDocument,
                       od.actualGoodsMovementDate AS deliveryDate,
                       od.overallGoodsMovementStatus AS goodsMovementStatus
                ORDER BY od.actualGoodsMovementDate DESC
                LIMIT 50
                """
            )
            results["no_billing"] = {
                "label":       "Deliveries not billed",
                "count":       len(rows),
                "description": "Outbound deliveries completed but not yet invoiced.",
                "rows":        rows,
            }

        if flow_type in ("all", "no_payment"):
            rows = _run_cypher(
                """
                MATCH (bd:BillingDocument)-[:RECORDED_IN]->(je:JournalEntry)
                WHERE NOT (je)-[:CLEARED_BY]->()
                  AND bd.billingDocumentIsCancelled = false
                RETURN bd.billingDocument     AS billingDocument,
                       bd.soldToParty         AS customer,
                       bd.totalNetAmount      AS amount,
                       bd.transactionCurrency AS currency,
                       bd.billingDocumentDate AS billingDate,
                       je.accountingDocument  AS accountingDocument
                ORDER BY bd.billingDocumentDate DESC
                LIMIT 50
                """
            )
            results["no_payment"] = {
                "label":       "Invoices not yet paid",
                "count":       len(rows),
                "description": "Billing documents recorded in accounting but not cleared by a payment.",
                "rows":        rows,
            }

        if flow_type in ("all", "cancelled"):
            rows = _run_cypher(
                """
                MATCH (bd:BillingDocument)
                WHERE bd.billingDocumentIsCancelled = true
                RETURN bd.billingDocument          AS billingDocument,
                       bd.soldToParty              AS customer,
                       bd.totalNetAmount           AS amount,
                       bd.transactionCurrency      AS currency,
                       bd.billingDocumentDate      AS billingDate,
                       bd.cancelledBillingDocument AS cancelledBy
                ORDER BY bd.billingDocumentDate DESC
                LIMIT 50
                """
            )
            results["cancelled"] = {
                "label":       "Cancelled billing documents",
                "count":       len(rows),
                "description": "Billing documents that have been cancelled.",
                "rows":        rows,
            }

        # Summary counts across all types
        summary = {k: v["count"] for k, v in results.items()}

        return {
            "summary":   summary,
            "results":   results,
        }

    except Exception as e:
        logger.error(f"Broken flows error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 3: Top Products by Billing Volume ───────────────────────────────────

@router.get("/top-products")
async def get_top_products(
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Returns products ranked by number of billing document items.
    Quick-access version of the most common example query.
    """
    try:
        rows = _run_cypher(
            """
            MATCH (bdi:BillingDocumentItem)-[:FOR_PRODUCT]->(p:Product)
            RETURN p.product          AS productId,
                   p.description      AS description,
                   p.productGroup     AS productGroup,
                   count(bdi)         AS billingCount,
                   sum(toFloat(bdi.netAmount)) AS totalRevenue
            ORDER BY billingCount DESC
            LIMIT $limit
            """,
            {"limit": limit}
        )
        return {"count": len(rows), "products": rows}

    except Exception as e:
        logger.error(f"Top products error: {e}")
        raise HTTPException(status_code=500, detail=str(e))