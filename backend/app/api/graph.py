import logging
from fastapi import APIRouter, HTTPException, Query
from app.core.database import get_driver

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/graph", tags=["Graph"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def serialize_node(node) -> dict:
    """
    Converts a Neo4j Node object into a plain dict the frontend can use.

    WHY THIS HELPER:
    Neo4j driver returns Node objects with special types.
    JSON serialization fails on these directly.
    We extract id, labels, and properties manually.
    """
    return {
        "id":         str(node.element_id),
        "labels":     list(node.labels),
        "properties": dict(node),
    }


def serialize_relationship(rel) -> dict:
    """Converts a Neo4j Relationship object into a plain dict."""
    return {
        "id":         str(rel.element_id),
        "type":       rel.type,
        "startNode":  str(rel.start_node.element_id),
        "endNode":    str(rel.end_node.element_id),
        "properties": dict(rel),
    }


# ── Route 1: Graph Overview ───────────────────────────────────────────────────

@router.get("/overview")
async def get_graph_overview(
    limit: int = Query(default=100, ge=10, le=300)
):
    """
    Returns the core O2C flow nodes only — excludes AVAILABLE_AT
    relationships which dominate the graph and obscure the main flow.
    """
    driver = get_driver()

    try:
        with driver.session() as session:
            result = session.run(
                    """
                    MATCH (n)
                    WHERE n:BusinessPartner
                    OR n:SalesOrder
                    OR n:OutboundDelivery
                    OR n:BillingDocument
                    OR n:JournalEntry
                    OR n:Payment
                    OR n:Product
                    WITH n LIMIT $limit

                    OPTIONAL MATCH (n)-[r]->(m)
                    WHERE type(r) IN [
                        'PLACED', 'FULFILLED_BY', 'BILLED_AS',
                        'RECORDED_IN', 'CLEARED_BY', 'BILLED_TO',
                        'FOR_PRODUCT', 'HAS_ITEM'
                    ]
                    RETURN
                        collect(DISTINCT n) AS nodes,
                        collect(DISTINCT m) AS targets,
                        collect(DISTINCT r) AS rels
                    """,
                    {"limit": limit}
                )

            row = result.single()
            if not row:
                return {"nodes": [], "edges": []}

            all_nodes: dict[str, dict] = {}
            for node in row["nodes"] + row["targets"]:
                if node is not None:
                    serialized = serialize_node(node)
                    all_nodes[serialized["id"]] = serialized

            edges = []
            for rel in row["rels"]:
                if rel is not None:
                    edges.append(serialize_relationship(rel))

            return {
                "nodes": list(all_nodes.values()),
                "edges": edges,
            }

    except Exception as e:
        logger.error(f"Graph overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Route 2: Node Detail + Neighbours ────────────────────────────────────────

@router.get("/node/{node_id}")
async def get_node(node_id: str):
    """
    Returns a single node's full properties plus all its
    immediate neighbours and connecting relationships.

    Used when the user clicks a node in the frontend to expand it.

    WHY element_id:
    Neo4j's internal element_id is a string like '4:abc123:0'.
    We use it as the stable identifier across requests.
    """
    driver = get_driver()

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE elementId(n) = $node_id
                OPTIONAL MATCH (n)-[r]-(neighbour)
                RETURN n AS node,
                       collect(DISTINCT neighbour) AS neighbours,
                       collect(DISTINCT r)          AS rels
                """,
                {"node_id": node_id}
            )

            row = result.single()
            if not row or row["node"] is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Node {node_id} not found"
                )

            node = serialize_node(row["node"])

            neighbours = [
                serialize_node(n)
                for n in row["neighbours"]
                if n is not None
            ]

            edges = [
                serialize_relationship(r)
                for r in row["rels"]
                if r is not None
            ]

            return {
                "node":        node,
                "neighbours":  neighbours,
                "edges":       edges,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Node detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 3: Search Nodes ─────────────────────────────────────────────────────

@router.get("/search")
async def search_nodes(
    q: str = Query(..., min_length=1, description="Search term")
):
    """
    Searches for nodes whose key identifier fields contain the query.

    Searches across:
    - SalesOrder.salesOrder
    - BillingDocument.billingDocument
    - OutboundDelivery.deliveryDocument
    - BusinessPartner.fullName
    - Product.description

    WHY CASE-INSENSITIVE CONTAINS:
    Users will search for partial IDs like '7405' or product names
    like 'sunscreen'. toLower() + CONTAINS handles both.
    """
    driver = get_driver()

    try:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (n)
                WHERE (n:SalesOrder        AND toLower(n.salesOrder)        CONTAINS toLower($q))
                   OR (n:BillingDocument   AND toLower(n.billingDocument)   CONTAINS toLower($q))
                   OR (n:OutboundDelivery  AND toLower(n.deliveryDocument)  CONTAINS toLower($q))
                   OR (n:BusinessPartner   AND toLower(n.fullName)          CONTAINS toLower($q))
                   OR (n:Product           AND toLower(n.description)       CONTAINS toLower($q))
                   OR (n:Plant             AND toLower(n.plantName)         CONTAINS toLower($q))
                RETURN n LIMIT 20
                """,
                {"q": q}
            )

            nodes = [serialize_node(row["n"]) for row in result]

            return {
                "query":   q,
                "count":   len(nodes),
                "results": nodes,
            }

    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Route 4: Node Stats ───────────────────────────────────────────────────────

@router.get("/stats")
async def get_graph_stats():
    """
    Returns a summary of node and relationship counts.
    Used by the frontend dashboard header.
    """
    driver = get_driver()

    try:
        with driver.session() as session:
            node_result = session.run(
                """
                MATCH (n)
                RETURN labels(n)[0] AS label, count(n) AS count
                ORDER BY count DESC
                """
            )
            nodes = {r["label"]: r["count"] for r in node_result}

            rel_result = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(r) AS count
                ORDER BY count DESC
                """
            )
            relationships = {r["type"]: r["count"] for r in rel_result}

            return {
                "nodes":         nodes,
                "relationships": relationships,
                "totals": {
                    "nodes":         sum(nodes.values()),
                    "relationships": sum(relationships.values()),
                }
            }

    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

