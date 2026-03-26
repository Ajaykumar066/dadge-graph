"""
ingest.py

Ingests all SAP O2C entities into Neo4j as a property graph.

STRUCTURE:
- create_constraints()       — run once before any ingestion
- clear_database()           — wipe graph for a clean re-run
- ingest_business_partners() — root node (customers)
- ingest_products()          — root node (materials)
- ... more functions added in subsequent steps

BATCH SIZE:
We send records to Neo4j in batches of 500 using UNWIND.
WHY: Sending 10,000 individual queries is slow. UNWIND lets
Neo4j process a list in a single transaction — ~10x faster.
"""

import logging
from neo4j import Driver
from app.graph.reader import iter_records, safe_str, make_composite_id

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # records per Neo4j transaction


# ── Batch helper ────────────────────────────────────────────────────────────

def _run_batch(driver: Driver, query: str, records: list[dict]) -> None:
    """
    Sends a list of records to Neo4j using UNWIND in a single transaction.

    WHY UNWIND:
    UNWIND $records AS row
    tells Neo4j: "iterate this list inside one transaction".
    Much faster than one session.run() per record.

    Args:
        driver:  active Neo4j driver
        query:   Cypher query using UNWIND $records AS row
        records: list of normalized dicts to send
    """
    if not records:
        return
    with driver.session() as session:
        session.run(query, {"records": records})


def _ingest_in_batches(
    driver: Driver,
    query: str,
    records: list[dict],
    label: str,
) -> int:
    """
    Splits records into batches of BATCH_SIZE and ingests each batch.

    Returns total number of records successfully sent.
    """
    total = len(records)
    if total == 0:
        logger.warning(f"  ⚠️  No records to ingest for {label}")
        return 0

    for i in range(0, total, BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        try:
            _run_batch(driver, query, batch)
        except Exception as e:
            logger.error(f"  ❌ Batch {i}–{i+len(batch)} failed for {label}: {e}")
            raise

    logger.info(f"  ✅ {label}: {total:,} records ingested")
    return total


# ── Schema setup ────────────────────────────────────────────────────────────

def create_constraints(driver: Driver) -> None:
    """
    Creates uniqueness constraints on every node's primary key.

    WHY THIS MUST RUN FIRST:
    1. Uniqueness constraints automatically create a B-tree index.
    2. MERGE on an indexed property is O(log n).
       MERGE without an index is a full graph scan — O(n).
    3. Without constraints, re-running ingestion creates duplicate nodes.

    The IF NOT EXISTS clause makes this safe to re-run.
    """
    logger.info("Setting up constraints and indexes...")

    constraints = [
        # Core business entities
        "CREATE CONSTRAINT bp_id IF NOT EXISTS "
        "FOR (n:BusinessPartner) REQUIRE n.businessPartner IS UNIQUE",

        "CREATE CONSTRAINT product_id IF NOT EXISTS "
        "FOR (n:Product) REQUIRE n.product IS UNIQUE",

        "CREATE CONSTRAINT plant_id IF NOT EXISTS "
        "FOR (n:Plant) REQUIRE n.plant IS UNIQUE",

        "CREATE CONSTRAINT address_id IF NOT EXISTS "
        "FOR (n:Address) REQUIRE n.addressId IS UNIQUE",

        # O2C flow nodes
        "CREATE CONSTRAINT so_id IF NOT EXISTS "
        "FOR (n:SalesOrder) REQUIRE n.salesOrder IS UNIQUE",

        "CREATE CONSTRAINT soi_id IF NOT EXISTS "
        "FOR (n:SalesOrderItem) REQUIRE n.itemId IS UNIQUE",

        "CREATE CONSTRAINT sosl_id IF NOT EXISTS "
        "FOR (n:SalesOrderScheduleLine) REQUIRE n.scheduleId IS UNIQUE",

        "CREATE CONSTRAINT od_id IF NOT EXISTS "
        "FOR (n:OutboundDelivery) REQUIRE n.deliveryDocument IS UNIQUE",

        "CREATE CONSTRAINT odi_id IF NOT EXISTS "
        "FOR (n:OutboundDeliveryItem) REQUIRE n.deliveryItemId IS UNIQUE",

        "CREATE CONSTRAINT bd_id IF NOT EXISTS "
        "FOR (n:BillingDocument) REQUIRE n.billingDocument IS UNIQUE",

        "CREATE CONSTRAINT bdi_id IF NOT EXISTS "
        "FOR (n:BillingDocumentItem) REQUIRE n.billingItemId IS UNIQUE",

        "CREATE CONSTRAINT je_id IF NOT EXISTS "
        "FOR (n:JournalEntry) REQUIRE n.journalEntryId IS UNIQUE",

        "CREATE CONSTRAINT pay_id IF NOT EXISTS "
        "FOR (n:Payment) REQUIRE n.paymentId IS UNIQUE",
    ]

    for cypher in constraints:
        try:
            with driver.session() as session:
                session.run(cypher)
        except Exception as e:
            # Constraint may already exist under a different name — not fatal
            logger.warning(f"  Constraint skipped (may already exist): {e}")

    logger.info("  ✅ All constraints ready")


def clear_database(driver: Driver) -> None:
    """
    Deletes all nodes and relationships from the graph.

    DETACH DELETE removes the node AND all its relationships atomically.
    Use only during development re-runs.
    """
    logger.info("Clearing existing graph data...")
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    logger.info("  ✅ Database cleared")


# ── Node: BusinessPartner ───────────────────────────────────────────────────

def ingest_business_partners(driver: Driver) -> int:
    """
    Ingests BusinessPartner nodes from two sources:
    - business_partners          (name, category, status)
    - business_partner_addresses (city, country, street)

    WHY TWO SOURCES:
    The SAP data model separates partner master data from address data.
    We denormalize both into a single node for simpler graph queries —
    no need to traverse to an Address node just to get a city name.
    We keep Address as a separate node too for completeness.

    Primary key: businessPartner (e.g. '310000108')
    """
    logger.info("Ingesting BusinessPartner nodes...")

    # Step 1: Load base partner data
    partners: dict[str, dict] = {}
    for r in iter_records("business_partners"):
        bp_id = safe_str(r.get("businessPartner"))
        if not bp_id:
            continue
        partners[bp_id] = {
            "businessPartner": bp_id,
            "customer":                 safe_str(r.get("customer")),
            "fullName":                 safe_str(r.get("businessPartnerFullName")),
            "name":                     safe_str(r.get("businessPartnerName")),
            "category":                 safe_str(r.get("businessPartnerCategory")),
            "grouping":                 safe_str(r.get("businessPartnerGrouping")),
            "isBlocked":                bool(r.get("businessPartnerIsBlocked", False)),
            "isMarkedForArchiving":     bool(r.get("isMarkedForArchiving", False)),
            "creationDate":             safe_str(r.get("creationDate")),
            # Address fields — will be filled from addresses below
            "cityName":    None,
            "country":     None,
            "region":      None,
            "streetName":  None,
            "postalCode":  None,
        }

    # Step 2: Enrich with address data (merge by businessPartner)
    for r in iter_records("business_partner_addresses"):
        bp_id = safe_str(r.get("businessPartner"))
        if bp_id and bp_id in partners:
            partners[bp_id]["cityName"]   = safe_str(r.get("cityName"))
            partners[bp_id]["country"]    = safe_str(r.get("country"))
            partners[bp_id]["region"]     = safe_str(r.get("region"))
            partners[bp_id]["streetName"] = safe_str(r.get("streetName"))
            partners[bp_id]["postalCode"] = safe_str(r.get("postalCode"))

    records = list(partners.values())

    query = """
    UNWIND $records AS row
    MERGE (bp:BusinessPartner {businessPartner: row.businessPartner})
    SET bp.customer             = row.customer,
        bp.fullName             = row.fullName,
        bp.name                 = row.name,
        bp.category             = row.category,
        bp.grouping             = row.grouping,
        bp.isBlocked            = row.isBlocked,
        bp.isMarkedForArchiving = row.isMarkedForArchiving,
        bp.creationDate         = row.creationDate,
        bp.cityName             = row.cityName,
        bp.country              = row.country,
        bp.region               = row.region,
        bp.streetName           = row.streetName,
        bp.postalCode           = row.postalCode,
        bp.nodeLabel            = 'BusinessPartner'
    """
    return _ingest_in_batches(driver, query, records, "BusinessPartner")


# ── Node: Product ───────────────────────────────────────────────────────────

def ingest_products(driver: Driver) -> int:
    """
    Ingests Product nodes from two sources:
    - products             (type, weight, group, division)
    - product_descriptions (human-readable name in English)

    WHY TWO SOURCES:
    SAP separates product master data from its text descriptions
    (because descriptions exist per language). We only want EN.

    Primary key: product (e.g. 'B8907367002246')
    """
    logger.info("Ingesting Product nodes...")

    # Step 1: Load base product data
    products: dict[str, dict] = {}
    for r in iter_records("products"):
        p_id = safe_str(r.get("product"))
        if not p_id:
            continue
        products[p_id] = {
            "product":          p_id,
            "productType":      safe_str(r.get("productType")),
            "productOldId":     safe_str(r.get("productOldId")),
            "grossWeight":      safe_str(r.get("grossWeight")),
            "netWeight":        safe_str(r.get("netWeight")),
            "weightUnit":       safe_str(r.get("weightUnit")),
            "productGroup":     safe_str(r.get("productGroup")),
            "baseUnit":         safe_str(r.get("baseUnit")),
            "division":         safe_str(r.get("division")),
            "industrySector":   safe_str(r.get("industrySector")),
            "isMarkedForDeletion": bool(r.get("isMarkedForDeletion", False)),
            # Description filled below
            "description": None,
        }

    # Step 2: Enrich with English descriptions only
    for r in iter_records("product_descriptions"):
        p_id = safe_str(r.get("product"))
        lang = safe_str(r.get("language"))
        if p_id and lang == "EN" and p_id in products:
            products[p_id]["description"] = safe_str(r.get("productDescription"))

    records = list(products.values())

    query = """
    UNWIND $records AS row
    MERGE (p:Product {product: row.product})
    SET p.productType         = row.productType,
        p.productOldId        = row.productOldId,
        p.description         = row.description,
        p.grossWeight         = row.grossWeight,
        p.netWeight           = row.netWeight,
        p.weightUnit          = row.weightUnit,
        p.productGroup        = row.productGroup,
        p.baseUnit            = row.baseUnit,
        p.division            = row.division,
        p.industrySector      = row.industrySector,
        p.isMarkedForDeletion = row.isMarkedForDeletion,
        p.nodeLabel           = 'Product'
    """
    return _ingest_in_batches(driver, query, records, "Product")

    # ── Node: Plant ─────────────────────────────────────────────────────────────

def ingest_plants(driver: Driver) -> int:
    """
    Ingests Plant nodes.

    Plants are physical warehouse/factory locations.
    They appear as the SHIPPED_FROM destination on OutboundDeliveryItems.

    Primary key: plant (e.g. 'WB05', '1920')
    """
    logger.info("Ingesting Plant nodes...")

    records = []
    for r in iter_records("plants"):
        plant_id = safe_str(r.get("plant"))
        if not plant_id:
            continue
        records.append({
            "plant":                        plant_id,
            "plantName":                    safe_str(r.get("plantName")),
            "salesOrganization":            safe_str(r.get("salesOrganization")),
            "distributionChannel":          safe_str(r.get("distributionChannel")),
            "division":                     safe_str(r.get("division")),
            "factoryCalendar":              safe_str(r.get("factoryCalendar")),
            "language":                     safe_str(r.get("language")),
            "isMarkedForArchiving":         bool(r.get("isMarkedForArchiving", False)),
        })

    query = """
    UNWIND $records AS row
    MERGE (pl:Plant {plant: row.plant})
    SET pl.plantName           = row.plantName,
        pl.salesOrganization   = row.salesOrganization,
        pl.distributionChannel = row.distributionChannel,
        pl.division            = row.division,
        pl.factoryCalendar     = row.factoryCalendar,
        pl.language            = row.language,
        pl.isMarkedForArchiving = row.isMarkedForArchiving,
        pl.nodeLabel           = 'Plant'
    """
    return _ingest_in_batches(driver, query, records, "Plant")


# ── Node: SalesOrder ────────────────────────────────────────────────────────

def ingest_sales_orders(driver: Driver) -> int:
    """
    Ingests SalesOrder header nodes.

    This is the entry point of the entire O2C flow.
    soldToParty links back to BusinessPartner.

    Primary key: salesOrder (e.g. '740506')
    """
    logger.info("Ingesting SalesOrder nodes...")

    records = []
    for r in iter_records("sales_order_headers"):
        so_id = safe_str(r.get("salesOrder"))
        if not so_id:
            continue
        records.append({
            "salesOrder":                   so_id,
            "soldToParty":                  safe_str(r.get("soldToParty")),
            "salesOrderType":               safe_str(r.get("salesOrderType")),
            "salesOrganization":            safe_str(r.get("salesOrganization")),
            "distributionChannel":          safe_str(r.get("distributionChannel")),
            "organizationDivision":         safe_str(r.get("organizationDivision")),
            "totalNetAmount":               safe_str(r.get("totalNetAmount")),
            "transactionCurrency":          safe_str(r.get("transactionCurrency")),
            "overallDeliveryStatus":        safe_str(r.get("overallDeliveryStatus")),
            "overallOrdReltdBillgStatus":   safe_str(r.get("overallOrdReltdBillgStatus")),
            "creationDate":                 safe_str(r.get("creationDate")),
            "requestedDeliveryDate":        safe_str(r.get("requestedDeliveryDate")),
            "incotermsClassification":      safe_str(r.get("incotermsClassification")),
            "customerPaymentTerms":         safe_str(r.get("customerPaymentTerms")),
            "headerBillingBlockReason":     safe_str(r.get("headerBillingBlockReason")),
            "deliveryBlockReason":          safe_str(r.get("deliveryBlockReason")),
        })

    query = """
    UNWIND $records AS row
    MERGE (so:SalesOrder {salesOrder: row.salesOrder})
    SET so.soldToParty               = row.soldToParty,
        so.salesOrderType            = row.salesOrderType,
        so.salesOrganization         = row.salesOrganization,
        so.distributionChannel       = row.distributionChannel,
        so.organizationDivision      = row.organizationDivision,
        so.totalNetAmount            = row.totalNetAmount,
        so.transactionCurrency       = row.transactionCurrency,
        so.overallDeliveryStatus     = row.overallDeliveryStatus,
        so.overallOrdReltdBillgStatus = row.overallOrdReltdBillgStatus,
        so.creationDate              = row.creationDate,
        so.requestedDeliveryDate     = row.requestedDeliveryDate,
        so.incotermsClassification   = row.incotermsClassification,
        so.customerPaymentTerms      = row.customerPaymentTerms,
        so.headerBillingBlockReason  = row.headerBillingBlockReason,
        so.deliveryBlockReason       = row.deliveryBlockReason,
        so.nodeLabel                 = 'SalesOrder'
    """
    return _ingest_in_batches(driver, query, records, "SalesOrder")


# ── Node: SalesOrderItem ────────────────────────────────────────────────────

def ingest_sales_order_items(driver: Driver) -> int:
    """
    Ingests SalesOrderItem nodes.

    WHY A COMPOSITE KEY:
    salesOrderItem ('10', '20', '30') is only unique WITHIN a salesOrder.
    Across the whole dataset, '10' appears hundreds of times.
    We combine salesOrder + salesOrderItem to make a globally unique ID.

    e.g. salesOrder='740506', salesOrderItem='10' → itemId='740506_10'

    Primary key: itemId (composite)
    FK to SalesOrder: salesOrder
    FK to Product: material
    """
    logger.info("Ingesting SalesOrderItem nodes...")

    records = []
    for r in iter_records("sales_order_items"):
        item_id = make_composite_id(
            r.get("salesOrder"),
            r.get("salesOrderItem")
        )
        if not item_id:
            continue
        records.append({
            "itemId":               item_id,
            "salesOrder":           safe_str(r.get("salesOrder")),
            "salesOrderItem":       safe_str(r.get("salesOrderItem")),
            "material":             safe_str(r.get("material")),
            "requestedQuantity":    safe_str(r.get("requestedQuantity")),
            "requestedQuantityUnit":safe_str(r.get("requestedQuantityUnit")),
            "netAmount":            safe_str(r.get("netAmount")),
            "transactionCurrency":  safe_str(r.get("transactionCurrency")),
            "materialGroup":        safe_str(r.get("materialGroup")),
            "productionPlant":      safe_str(r.get("productionPlant")),
            "storageLocation":      safe_str(r.get("storageLocation")),
            "itemBillingBlockReason": safe_str(r.get("itemBillingBlockReason")),
            "salesDocumentRjcnReason": safe_str(r.get("salesDocumentRjcnReason")),
        })

    query = """
    UNWIND $records AS row
    MERGE (soi:SalesOrderItem {itemId: row.itemId})
    SET soi.salesOrder            = row.salesOrder,
        soi.salesOrderItem        = row.salesOrderItem,
        soi.material              = row.material,
        soi.requestedQuantity     = row.requestedQuantity,
        soi.requestedQuantityUnit = row.requestedQuantityUnit,
        soi.netAmount             = row.netAmount,
        soi.transactionCurrency   = row.transactionCurrency,
        soi.materialGroup         = row.materialGroup,
        soi.productionPlant       = row.productionPlant,
        soi.storageLocation       = row.storageLocation,
        soi.itemBillingBlockReason   = row.itemBillingBlockReason,
        soi.salesDocumentRjcnReason  = row.salesDocumentRjcnReason,
        soi.nodeLabel             = 'SalesOrderItem'
    """
    return _ingest_in_batches(driver, query, records, "SalesOrderItem")

    # ── Node: SalesOrderScheduleLine ────────────────────────────────────────────

def ingest_schedule_lines(driver: Driver) -> int:
    """
    Ingests SalesOrderScheduleLine nodes.

    WHY SCHEDULE LINES EXIST IN SAP:
    A single SalesOrderItem can have multiple delivery dates.
    e.g. Item '10' for 100 units — 50 units on March 31, 50 on April 15.
    Each split is a schedule line. They carry the confirmed delivery date
    and confirmed quantity after material availability check (ATP check).

    Primary key: scheduleId (composite: salesOrder_salesOrderItem_scheduleLine)
    e.g. '740506_10_1'
    """
    logger.info("Ingesting SalesOrderScheduleLine nodes...")

    records = []
    for r in iter_records("sales_order_schedule_lines"):
        schedule_id = make_composite_id(
            r.get("salesOrder"),
            r.get("salesOrderItem"),
            r.get("scheduleLine"),
        )
        if not schedule_id:
            continue
        records.append({
            "scheduleId":                       schedule_id,
            "salesOrder":                       safe_str(r.get("salesOrder")),
            "salesOrderItem":                   safe_str(r.get("salesOrderItem")),
            "scheduleLine":                     safe_str(r.get("scheduleLine")),
            "confirmedDeliveryDate":            safe_str(r.get("confirmedDeliveryDate")),
            "orderQuantityUnit":                safe_str(r.get("orderQuantityUnit")),
            "confdOrderQtyByMatlAvailCheck":    safe_str(r.get("confdOrderQtyByMatlAvailCheck")),
        })

    query = """
    UNWIND $records AS row
    MERGE (sl:SalesOrderScheduleLine {scheduleId: row.scheduleId})
    SET sl.salesOrder                    = row.salesOrder,
        sl.salesOrderItem                = row.salesOrderItem,
        sl.scheduleLine                  = row.scheduleLine,
        sl.confirmedDeliveryDate         = row.confirmedDeliveryDate,
        sl.orderQuantityUnit             = row.orderQuantityUnit,
        sl.confdOrderQtyByMatlAvailCheck = row.confdOrderQtyByMatlAvailCheck,
        sl.nodeLabel                     = 'SalesOrderScheduleLine'
    """
    return _ingest_in_batches(driver, query, records, "SalesOrderScheduleLine")


# ── Node: OutboundDelivery ───────────────────────────────────────────────────

def ingest_outbound_deliveries(driver: Driver) -> int:
    """
    Ingests OutboundDelivery header nodes.

    WHY SEPARATE HEADER AND ITEMS:
    SAP splits delivery data into a header (one per shipment) and items
    (one per product line within that shipment). The header carries
    overall status; items carry product + plant details.

    The link back to SalesOrder is NOT on the header — it's on the item
    via referenceSdDocument. So OutboundDelivery connects to SalesOrder
    only indirectly through its items. We store this correctly in the
    relationship phase.

    Primary key: deliveryDocument (e.g. '80737721')
    """
    logger.info("Ingesting OutboundDelivery nodes...")

    records = []
    for r in iter_records("outbound_delivery_headers"):
        doc_id = safe_str(r.get("deliveryDocument"))
        if not doc_id:
            continue
        records.append({
            "deliveryDocument":             doc_id,
            "shippingPoint":                safe_str(r.get("shippingPoint")),
            "overallGoodsMovementStatus":   safe_str(r.get("overallGoodsMovementStatus")),
            "overallPickingStatus":         safe_str(r.get("overallPickingStatus")),
            "overallProofOfDeliveryStatus": safe_str(r.get("overallProofOfDeliveryStatus")),
            "actualGoodsMovementDate":      safe_str(r.get("actualGoodsMovementDate")),
            "creationDate":                 safe_str(r.get("creationDate")),
            "lastChangeDate":               safe_str(r.get("lastChangeDate")),
            "deliveryBlockReason":          safe_str(r.get("deliveryBlockReason")),
            "headerBillingBlockReason":     safe_str(r.get("headerBillingBlockReason")),
            "hdrGeneralIncompletionStatus": safe_str(r.get("hdrGeneralIncompletionStatus")),
        })

    query = """
    UNWIND $records AS row
    MERGE (od:OutboundDelivery {deliveryDocument: row.deliveryDocument})
    SET od.shippingPoint                = row.shippingPoint,
        od.overallGoodsMovementStatus   = row.overallGoodsMovementStatus,
        od.overallPickingStatus         = row.overallPickingStatus,
        od.overallProofOfDeliveryStatus = row.overallProofOfDeliveryStatus,
        od.actualGoodsMovementDate      = row.actualGoodsMovementDate,
        od.creationDate                 = row.creationDate,
        od.lastChangeDate               = row.lastChangeDate,
        od.deliveryBlockReason          = row.deliveryBlockReason,
        od.headerBillingBlockReason     = row.headerBillingBlockReason,
        od.hdrGeneralIncompletionStatus = row.hdrGeneralIncompletionStatus,
        od.nodeLabel                    = 'OutboundDelivery'
    """
    return _ingest_in_batches(driver, query, records, "OutboundDelivery")


# ── Node: OutboundDeliveryItem ───────────────────────────────────────────────

def ingest_outbound_delivery_items(driver: Driver) -> int:
    """
    Ingests OutboundDeliveryItem nodes.

    This is the most important bridge node in the entire graph:

    referenceSdDocument → links to SalesOrder (confirmed by our check:
                          deliveryDoc 80738076 → salesOrder 740556)

    This means:
    SalesOrder -[via ODI.referenceSdDocument]-> OutboundDelivery
    is the primary delivery fulfillment chain.

    plant → links to Plant (where the item was shipped from)

    Primary key: deliveryItemId
                 composite of deliveryDocument + deliveryDocumentItem
                 e.g. '80738076_000010'
    """
    logger.info("Ingesting OutboundDeliveryItem nodes...")

    records = []
    for r in iter_records("outbound_delivery_items"):
        item_id = make_composite_id(
            r.get("deliveryDocument"),
            r.get("deliveryDocumentItem"),
        )
        if not item_id:
            continue
        records.append({
            "deliveryItemId":           item_id,
            "deliveryDocument":         safe_str(r.get("deliveryDocument")),
            "deliveryDocumentItem":     safe_str(r.get("deliveryDocumentItem")),
            # FK back to SalesOrder
            "referenceSdDocument":      safe_str(r.get("referenceSdDocument")),
            "referenceSdDocumentItem":  safe_str(r.get("referenceSdDocumentItem")),
            # FK to Plant
            "plant":                    safe_str(r.get("plant")),
            "storageLocation":          safe_str(r.get("storageLocation")),
            "actualDeliveryQuantity":   safe_str(r.get("actualDeliveryQuantity")),
            "deliveryQuantityUnit":     safe_str(r.get("deliveryQuantityUnit")),
            "batch":                    safe_str(r.get("batch")),
            "itemBillingBlockReason":   safe_str(r.get("itemBillingBlockReason")),
        })

    query = """
    UNWIND $records AS row
    MERGE (odi:OutboundDeliveryItem {deliveryItemId: row.deliveryItemId})
    SET odi.deliveryDocument        = row.deliveryDocument,
        odi.deliveryDocumentItem    = row.deliveryDocumentItem,
        odi.referenceSdDocument     = row.referenceSdDocument,
        odi.referenceSdDocumentItem = row.referenceSdDocumentItem,
        odi.plant                   = row.plant,
        odi.storageLocation         = row.storageLocation,
        odi.actualDeliveryQuantity  = row.actualDeliveryQuantity,
        odi.deliveryQuantityUnit    = row.deliveryQuantityUnit,
        odi.batch                   = row.batch,
        odi.itemBillingBlockReason  = row.itemBillingBlockReason,
        odi.nodeLabel               = 'OutboundDeliveryItem'
    """
    return _ingest_in_batches(driver, query, records, "OutboundDeliveryItem")

    # ── Node: BillingDocument ────────────────────────────────────────────────────

def ingest_billing_documents(driver: Driver) -> int:
    """
    Ingests BillingDocument header nodes from TWO sources:
    - billing_document_headers      (active invoices)
    - billing_document_cancellations (cancelled invoices)

    WHY MERGE BOTH INTO ONE LABEL:
    Cancelled billing documents are still part of the O2C flow —
    they represent failed or reversed billing attempts.
    We use billingDocumentIsCancelled=True to distinguish them.
    This lets the LLM answer: "which orders have cancelled invoices?"
    without needing to traverse two separate node types.

    accountingDocument → FK to JournalEntry
    soldToParty        → FK to BusinessPartner

    Primary key: billingDocument (e.g. '90504248')
    """
    logger.info("Ingesting BillingDocument nodes...")

    # Use a dict to deduplicate — a doc could appear in both files
    billing_docs: dict[str, dict] = {}

    for source in ["billing_document_headers", "billing_document_cancellations"]:
        for r in iter_records(source):
            doc_id = safe_str(r.get("billingDocument"))
            if not doc_id:
                continue
            # Only update if not already loaded from headers
            # (headers take priority over cancellations)
            if doc_id not in billing_docs:
                billing_docs[doc_id] = {
                    "billingDocument":          doc_id,
                    "billingDocumentType":      safe_str(r.get("billingDocumentType")),
                    "soldToParty":              safe_str(r.get("soldToParty")),
                    "accountingDocument":       safe_str(r.get("accountingDocument")),
                    "cancelledBillingDocument": safe_str(r.get("cancelledBillingDocument")),
                    "totalNetAmount":           safe_str(r.get("totalNetAmount")),
                    "transactionCurrency":      safe_str(r.get("transactionCurrency")),
                    "billingDocumentDate":      safe_str(r.get("billingDocumentDate")),
                    "creationDate":             safe_str(r.get("creationDate")),
                    "companyCode":              safe_str(r.get("companyCode")),
                    "fiscalYear":               safe_str(r.get("fiscalYear")),
                    "billingDocumentIsCancelled": bool(
                        r.get("billingDocumentIsCancelled", False)
                    ),
                }

    records = list(billing_docs.values())

    query = """
    UNWIND $records AS row
    MERGE (bd:BillingDocument {billingDocument: row.billingDocument})
    SET bd.billingDocumentType       = row.billingDocumentType,
        bd.soldToParty               = row.soldToParty,
        bd.accountingDocument        = row.accountingDocument,
        bd.cancelledBillingDocument  = row.cancelledBillingDocument,
        bd.totalNetAmount            = row.totalNetAmount,
        bd.transactionCurrency       = row.transactionCurrency,
        bd.billingDocumentDate       = row.billingDocumentDate,
        bd.creationDate              = row.creationDate,
        bd.companyCode               = row.companyCode,
        bd.fiscalYear                = row.fiscalYear,
        bd.billingDocumentIsCancelled = row.billingDocumentIsCancelled,
        bd.nodeLabel                 = 'BillingDocument'
    """
    return _ingest_in_batches(driver, query, records, "BillingDocument")


# ── Node: BillingDocumentItem ────────────────────────────────────────────────

def ingest_billing_document_items(driver: Driver) -> int:
    """
    Ingests BillingDocumentItem nodes.

    KEY FK CONFIRMED IN STEP 2:
    referenceSdDocument → OutboundDelivery.deliveryDocument
    e.g. billingDoc '90504298' references delivery '80738109'

    This is the bridge that connects billing back to delivery.
    Without this link, you cannot trace:
    SalesOrder → Delivery → BillingDocument

    material → FK to Product

    Primary key: billingItemId
                 composite of billingDocument + billingDocumentItem
                 e.g. '90504298_10'
    """
    logger.info("Ingesting BillingDocumentItem nodes...")

    records = []
    for r in iter_records("billing_document_items"):
        item_id = make_composite_id(
            r.get("billingDocument"),
            r.get("billingDocumentItem"),
        )
        if not item_id:
            continue
        records.append({
            "billingItemId":            item_id,
            "billingDocument":          safe_str(r.get("billingDocument")),
            "billingDocumentItem":      safe_str(r.get("billingDocumentItem")),
            # FK to OutboundDelivery
            "referenceSdDocument":      safe_str(r.get("referenceSdDocument")),
            "referenceSdDocumentItem":  safe_str(r.get("referenceSdDocumentItem")),
            # FK to Product
            "material":                 safe_str(r.get("material")),
            "netAmount":                safe_str(r.get("netAmount")),
            "billingQuantity":          safe_str(r.get("billingQuantity")),
            "billingQuantityUnit":      safe_str(r.get("billingQuantityUnit")),
            "transactionCurrency":      safe_str(r.get("transactionCurrency")),
        })

    query = """
    UNWIND $records AS row
    MERGE (bdi:BillingDocumentItem {billingItemId: row.billingItemId})
    SET bdi.billingDocument         = row.billingDocument,
        bdi.billingDocumentItem     = row.billingDocumentItem,
        bdi.referenceSdDocument     = row.referenceSdDocument,
        bdi.referenceSdDocumentItem = row.referenceSdDocumentItem,
        bdi.material                = row.material,
        bdi.netAmount               = row.netAmount,
        bdi.billingQuantity         = row.billingQuantity,
        bdi.billingQuantityUnit     = row.billingQuantityUnit,
        bdi.transactionCurrency     = row.transactionCurrency,
        bdi.nodeLabel               = 'BillingDocumentItem'
    """
    return _ingest_in_batches(driver, query, records, "BillingDocumentItem")


# ── Node: JournalEntry ───────────────────────────────────────────────────────

def ingest_journal_entries(driver: Driver) -> int:
    """
    Ingests JournalEntry nodes from journal_entry_items_accounts_receivable.

    WHY JOURNAL ENTRIES MATTER:
    In SAP, every billing document automatically creates an accounting
    document (journal entry) in the general ledger. This is the financial
    record of the revenue.

    referenceDocument → FK to BillingDocument
                        (confirmed: referenceDocument '90504219'
                         matches billingDocument '90504219')

    clearingAccountingDocument → FK to Payment
                                 (the payment that cleared this entry)

    customer → FK to BusinessPartner

    Primary key: journalEntryId
                 composite of accountingDocument + accountingDocumentItem
                 e.g. '9400000220_1'
    """
    logger.info("Ingesting JournalEntry nodes...")

    records = []
    for r in iter_records("journal_entry_items_accounts_receivable"):
        je_id = make_composite_id(
            r.get("accountingDocument"),
            r.get("accountingDocumentItem"),
        )
        if not je_id:
            continue
        records.append({
            "journalEntryId":               je_id,
            "accountingDocument":           safe_str(r.get("accountingDocument")),
            "accountingDocumentItem":       safe_str(r.get("accountingDocumentItem")),
            "companyCode":                  safe_str(r.get("companyCode")),
            "fiscalYear":                   safe_str(r.get("fiscalYear")),
            "glAccount":                    safe_str(r.get("glAccount")),
            # FK to BillingDocument
            "referenceDocument":            safe_str(r.get("referenceDocument")),
            # FK to Payment
            "clearingAccountingDocument":   safe_str(r.get("clearingAccountingDocument")),
            "clearingDocFiscalYear":        safe_str(r.get("clearingDocFiscalYear")),
            # FK to BusinessPartner
            "customer":                     safe_str(r.get("customer")),
            "amountInTransactionCurrency":  safe_str(r.get("amountInTransactionCurrency")),
            "transactionCurrency":          safe_str(r.get("transactionCurrency")),
            "amountInCompanyCodeCurrency":  safe_str(r.get("amountInCompanyCodeCurrency")),
            "postingDate":                  safe_str(r.get("postingDate")),
            "documentDate":                 safe_str(r.get("documentDate")),
            "clearingDate":                 safe_str(r.get("clearingDate")),
            "accountingDocumentType":       safe_str(r.get("accountingDocumentType")),
            "profitCenter":                 safe_str(r.get("profitCenter")),
            "financialAccountType":         safe_str(r.get("financialAccountType")),
        })

    query = """
    UNWIND $records AS row
    MERGE (je:JournalEntry {journalEntryId: row.journalEntryId})
    SET je.accountingDocument          = row.accountingDocument,
        je.accountingDocumentItem      = row.accountingDocumentItem,
        je.companyCode                 = row.companyCode,
        je.fiscalYear                  = row.fiscalYear,
        je.glAccount                   = row.glAccount,
        je.referenceDocument           = row.referenceDocument,
        je.clearingAccountingDocument  = row.clearingAccountingDocument,
        je.clearingDocFiscalYear       = row.clearingDocFiscalYear,
        je.customer                    = row.customer,
        je.amountInTransactionCurrency = row.amountInTransactionCurrency,
        je.transactionCurrency         = row.transactionCurrency,
        je.amountInCompanyCodeCurrency = row.amountInCompanyCodeCurrency,
        je.postingDate                 = row.postingDate,
        je.documentDate                = row.documentDate,
        je.clearingDate                = row.clearingDate,
        je.accountingDocumentType      = row.accountingDocumentType,
        je.profitCenter                = row.profitCenter,
        je.financialAccountType        = row.financialAccountType,
        je.nodeLabel                   = 'JournalEntry'
    """
    return _ingest_in_batches(driver, query, records, "JournalEntry")


# ── Node: Payment ────────────────────────────────────────────────────────────

def ingest_payments(driver: Driver) -> int:
    """
    Ingests Payment nodes from payments_accounts_receivable.

    HOW PAYMENTS LINK TO THE REST OF THE GRAPH:
    A payment in SAP clears one or more journal entries.
    The link is:
      Payment.clearingAccountingDocument
        = JournalEntry.clearingAccountingDocument

    Both sides store the same clearing document number —
    that's the join key between them.

    accountingDocument → the original AR document being paid
    customer           → FK to BusinessPartner

    WHY COMPOSITE KEY:
    clearingAccountingDocument alone is not unique per row —
    one payment document can clear multiple line items.
    We combine it with accountingDocumentItem for uniqueness.

    Primary key: paymentId
                 composite of clearingAccountingDocument + accountingDocumentItem
                 e.g. '9400635977_1'
    """
    logger.info("Ingesting Payment nodes...")

    records = []
    for r in iter_records("payments_accounts_receivable"):
        payment_id = make_composite_id(
            r.get("clearingAccountingDocument"),
            r.get("accountingDocumentItem"),
        )
        if not payment_id:
            continue
        records.append({
            "paymentId":                    payment_id,
            "clearingAccountingDocument":   safe_str(r.get("clearingAccountingDocument")),
            "accountingDocumentItem":       safe_str(r.get("accountingDocumentItem")),
            # FK to JournalEntry (the AR doc being cleared)
            "accountingDocument":           safe_str(r.get("accountingDocument")),
            # FK to BusinessPartner
            "customer":                     safe_str(r.get("customer")),
            "companyCode":                  safe_str(r.get("companyCode")),
            "fiscalYear":                   safe_str(r.get("fiscalYear")),
            "clearingDate":                 safe_str(r.get("clearingDate")),
            "clearingDocFiscalYear":        safe_str(r.get("clearingDocFiscalYear")),
            "postingDate":                  safe_str(r.get("postingDate")),
            "documentDate":                 safe_str(r.get("documentDate")),
            "amountInTransactionCurrency":  safe_str(r.get("amountInTransactionCurrency")),
            "transactionCurrency":          safe_str(r.get("transactionCurrency")),
            "amountInCompanyCodeCurrency":  safe_str(r.get("amountInCompanyCodeCurrency")),
            "glAccount":                    safe_str(r.get("glAccount")),
            "profitCenter":                 safe_str(r.get("profitCenter")),
            "financialAccountType":         safe_str(r.get("financialAccountType")),
        })

    query = """
    UNWIND $records AS row
    MERGE (pay:Payment {paymentId: row.paymentId})
    SET pay.clearingAccountingDocument  = row.clearingAccountingDocument,
        pay.accountingDocumentItem      = row.accountingDocumentItem,
        pay.accountingDocument          = row.accountingDocument,
        pay.customer                    = row.customer,
        pay.companyCode                 = row.companyCode,
        pay.fiscalYear                  = row.fiscalYear,
        pay.clearingDate                = row.clearingDate,
        pay.clearingDocFiscalYear       = row.clearingDocFiscalYear,
        pay.postingDate                 = row.postingDate,
        pay.documentDate                = row.documentDate,
        pay.amountInTransactionCurrency = row.amountInTransactionCurrency,
        pay.transactionCurrency         = row.transactionCurrency,
        pay.amountInCompanyCodeCurrency = row.amountInCompanyCodeCurrency,
        pay.glAccount                   = row.glAccount,
        pay.profitCenter                = row.profitCenter,
        pay.financialAccountType        = row.financialAccountType,
        pay.nodeLabel                   = 'Payment'
    """
    return _ingest_in_batches(driver, query, records, "Payment")


    # ── Relationships ────────────────────────────────────────────────────────────

def create_relationships(driver: Driver) -> None:
    """
    Creates all edges between nodes.

    PATTERN USED THROUGHOUT:
        MATCH (a:LabelA), (b:LabelB)
        WHERE a.fkField = b.pkField
          AND a.fkField IS NOT NULL
        MERGE (a)-[:RELATIONSHIP]->(b)

    WHY MATCH + WHERE instead of MATCH with inline condition:
    - MATCH (a:LabelA {field: value}) requires knowing the value upfront
    - MATCH ... WHERE a.field = b.field lets Neo4j use indexes on BOTH
      sides simultaneously — much faster for bulk relationship creation

    WHY MERGE on relationships:
    - Safe to re-run without creating duplicate edges
    - Idempotent — same result every time

    WHY NOT NULL CHECK:
    - Some FK fields are None (e.g. optional references)
    - Without the IS NOT NULL guard, Neo4j would try to match
      nodes where both sides have a null property — wrong behavior
    """

    relationships = [

        # ── 1. BusinessPartner PLACED SalesOrder ──────────────────────────
        # soldToParty on SalesOrder matches businessPartner on BusinessPartner
        (
            "BusinessPartner -[PLACED]-> SalesOrder",
            """
            MATCH (bp:BusinessPartner), (so:SalesOrder)
            WHERE so.soldToParty = bp.businessPartner
              AND so.soldToParty IS NOT NULL
            MERGE (bp)-[:PLACED]->(so)
            """
        ),

        # ── 2. SalesOrder HAS_ITEM SalesOrderItem ─────────────────────────
        (
            "SalesOrder -[HAS_ITEM]-> SalesOrderItem",
            """
            MATCH (so:SalesOrder), (soi:SalesOrderItem)
            WHERE soi.salesOrder = so.salesOrder
              AND soi.salesOrder IS NOT NULL
            MERGE (so)-[:HAS_ITEM]->(soi)
            """
        ),

        # ── 3. SalesOrderItem FOR_PRODUCT Product ─────────────────────────
        # material on SalesOrderItem matches product on Product
        (
            "SalesOrderItem -[FOR_PRODUCT]-> Product",
            """
            MATCH (soi:SalesOrderItem), (p:Product)
            WHERE soi.material = p.product
              AND soi.material IS NOT NULL
            MERGE (soi)-[:FOR_PRODUCT]->(p)
            """
        ),

        # ── 4. SalesOrder HAS_SCHEDULE_LINE SalesOrderScheduleLine ────────
        (
            "SalesOrder -[HAS_SCHEDULE_LINE]-> SalesOrderScheduleLine",
            """
            MATCH (so:SalesOrder), (sl:SalesOrderScheduleLine)
            WHERE sl.salesOrder = so.salesOrder
              AND sl.salesOrder IS NOT NULL
            MERGE (so)-[:HAS_SCHEDULE_LINE]->(sl)
            """
        ),

        # ── 5. OutboundDelivery HAS_ITEM OutboundDeliveryItem ─────────────
        (
            "OutboundDelivery -[HAS_ITEM]-> OutboundDeliveryItem",
            """
            MATCH (od:OutboundDelivery), (odi:OutboundDeliveryItem)
            WHERE odi.deliveryDocument = od.deliveryDocument
              AND odi.deliveryDocument IS NOT NULL
            MERGE (od)-[:HAS_ITEM]->(odi)
            """
        ),

        # ── 6. SalesOrder FULFILLED_BY OutboundDelivery ───────────────────
        # This is the KEY relationship confirmed in Step 2:
        # OutboundDeliveryItem.referenceSdDocument = SalesOrder.salesOrder
        # We connect at the HEADER level for simpler graph traversal:
        # SalesOrder → OutboundDelivery (via their shared items)
        (
            "SalesOrder -[FULFILLED_BY]-> OutboundDelivery",
            """
            MATCH (so:SalesOrder), (odi:OutboundDeliveryItem),
                  (od:OutboundDelivery)
            WHERE odi.referenceSdDocument = so.salesOrder
              AND odi.deliveryDocument    = od.deliveryDocument
              AND odi.referenceSdDocument IS NOT NULL
            MERGE (so)-[:FULFILLED_BY]->(od)
            """
        ),

        # ── 7. OutboundDeliveryItem SHIPPED_FROM Plant ────────────────────
        (
            "OutboundDeliveryItem -[SHIPPED_FROM]-> Plant",
            """
            MATCH (odi:OutboundDeliveryItem), (pl:Plant)
            WHERE odi.plant = pl.plant
              AND odi.plant IS NOT NULL
            MERGE (odi)-[:SHIPPED_FROM]->(pl)
            """
        ),

        # ── 8. OutboundDelivery BILLED_AS BillingDocument ─────────────────
        # Confirmed in Step 2:
        # BillingDocumentItem.referenceSdDocument = OutboundDelivery.deliveryDocument
        # Again we connect at header level for cleaner traversal
        (
            "OutboundDelivery -[BILLED_AS]-> BillingDocument",
            """
            MATCH (od:OutboundDelivery), (bdi:BillingDocumentItem),
                  (bd:BillingDocument)
            WHERE bdi.referenceSdDocument = od.deliveryDocument
              AND bdi.billingDocument     = bd.billingDocument
              AND bdi.referenceSdDocument IS NOT NULL
            MERGE (od)-[:BILLED_AS]->(bd)
            """
        ),

        # ── 9. BillingDocument HAS_ITEM BillingDocumentItem ───────────────
        (
            "BillingDocument -[HAS_ITEM]-> BillingDocumentItem",
            """
            MATCH (bd:BillingDocument), (bdi:BillingDocumentItem)
            WHERE bdi.billingDocument = bd.billingDocument
              AND bdi.billingDocument IS NOT NULL
            MERGE (bd)-[:HAS_ITEM]->(bdi)
            """
        ),

        # ── 10. BillingDocumentItem FOR_PRODUCT Product ───────────────────
        (
            "BillingDocumentItem -[FOR_PRODUCT]-> Product",
            """
            MATCH (bdi:BillingDocumentItem), (p:Product)
            WHERE bdi.material = p.product
              AND bdi.material IS NOT NULL
            MERGE (bdi)-[:FOR_PRODUCT]->(p)
            """
        ),

        # ── 11. BillingDocument BILLED_TO BusinessPartner ─────────────────
        (
            "BillingDocument -[BILLED_TO]-> BusinessPartner",
            """
            MATCH (bd:BillingDocument), (bp:BusinessPartner)
            WHERE bd.soldToParty = bp.businessPartner
              AND bd.soldToParty IS NOT NULL
            MERGE (bd)-[:BILLED_TO]->(bp)
            """
        ),

        # ── 12. BillingDocument RECORDED_IN JournalEntry ──────────────────
        # accountingDocument on BillingDocument matches
        # referenceDocument on JournalEntry
        (
            "BillingDocument -[RECORDED_IN]-> JournalEntry",
            """
            MATCH (bd:BillingDocument), (je:JournalEntry)
            WHERE je.referenceDocument = bd.billingDocument
              AND je.referenceDocument IS NOT NULL
            MERGE (bd)-[:RECORDED_IN]->(je)
            """
        ),

        # ── 13. JournalEntry CLEARED_BY Payment ───────────────────────────
        # Both sides store clearingAccountingDocument —
        # that is the shared key linking AR entry to its payment
        (
            "JournalEntry -[CLEARED_BY]-> Payment",
            """
            MATCH (je:JournalEntry), (pay:Payment)
            WHERE je.clearingAccountingDocument = pay.clearingAccountingDocument
              AND je.accountingDocument         = pay.accountingDocument
              AND je.clearingAccountingDocument IS NOT NULL
            MERGE (je)-[:CLEARED_BY]->(pay)
            """
        ),

        # ── 14. Product AVAILABLE_AT Plant ────────────────────────────────
        # product_plants links products to the plants that stock them
        (
            "Product -[AVAILABLE_AT]-> Plant",
            """
            MATCH (p:Product), (pl:Plant)
            WHERE EXISTS {
                MATCH (p)-[:AVAILABLE_AT]->(pl)
            }
            RETURN count(*) AS already_exists
            """
            # This one is handled separately below via product_plants file
        ),

    ]

    logger.info("Creating relationships...")

    # Run all standard relationships
    for name, query in relationships[:-1]:   # skip last — handled separately
        try:
            with driver.session() as session:
                session.run(query)
            logger.info(f"  ✅ {name}")
        except Exception as e:
            logger.error(f"  ❌ Failed: {name} — {e}")
            raise

    # ── 14. Product AVAILABLE_AT Plant (from product_plants file) ─────────
    # This needs batch processing because product_plants has 3,036 records
    logger.info("  Creating Product -[AVAILABLE_AT]-> Plant (batch)...")
    pp_records = []
    for r in iter_records("product_plants"):
        product_id = safe_str(r.get("product"))
        plant_id   = safe_str(r.get("plant"))
        if product_id and plant_id:
            pp_records.append({
                "product": product_id,
                "plant":   plant_id,
            })

    pp_query = """
    UNWIND $records AS row
    MATCH (p:Product {product: row.product})
    MATCH (pl:Plant  {plant:   row.plant})
    MERGE (p)-[:AVAILABLE_AT]->(pl)
    """
    _ingest_in_batches(driver, pp_query, pp_records, "Product-AVAILABLE_AT-Plant")

    logger.info("  ✅ All relationships created")

    # ── Validation ───────────────────────────────────────────────────────────────

def validate_graph(driver: Driver) -> None:
    """
    Runs a full health check on the graph and prints a human-readable
    summary. Call this after create_relationships() to confirm the
    graph is correctly connected before building the API.
    """
    logger.info("\n" + "=" * 55)
    logger.info("  GRAPH VALIDATION REPORT")
    logger.info("=" * 55)

    with driver.session() as session:

        # ── Node counts ───────────────────────────────────────
        logger.info("\n📦 NODE COUNTS:")
        result = session.run("""
            MATCH (n)
            RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY count DESC
        """)
        for r in result:
            logger.info(f"   {r['label']:<30} {r['count']:>6,}")

        # ── Relationship counts ───────────────────────────────
        logger.info("\n🔗 RELATIONSHIP COUNTS:")
        result = session.run("""
            MATCH ()-[r]->()
            RETURN type(r) AS rel, count(r) AS count
            ORDER BY count DESC
        """)
        for r in result:
            logger.info(f"   {r['rel']:<30} {r['count']:>6,}")

        # ── Full O2C chain count ──────────────────────────────
        logger.info("\n✅ COMPLETE O2C FLOWS:")
        result = session.run("""
            MATCH (bp:BusinessPartner)-[:PLACED]->(so:SalesOrder)
                  -[:FULFILLED_BY]->(od:OutboundDelivery)
                  -[:BILLED_AS]->(bd:BillingDocument)
                  -[:RECORDED_IN]->(je:JournalEntry)
                  -[:CLEARED_BY]->(pay:Payment)
            RETURN count(*) AS complete_flows
        """)
        r = result.single()
        logger.info(f"   Full chain paths found:        {r['complete_flows']:>6,}")

        # ── Broken flow: delivered but not billed ─────────────
        logger.info("\n⚠️  BROKEN FLOWS:")
        result = session.run("""
            MATCH (so:SalesOrder)-[:FULFILLED_BY]->(od:OutboundDelivery)
            WHERE NOT (od)-[:BILLED_AS]->()
            RETURN count(*) AS count
        """)
        r = result.single()
        logger.info(f"   Delivered but not billed:      {r['count']:>6,}")

        # ── Broken flow: billed but no delivery ───────────────
        result = session.run("""
            MATCH (so:SalesOrder)-[:HAS_ITEM]->(soi:SalesOrderItem)
            WHERE NOT (so)-[:FULFILLED_BY]->()
            RETURN count(DISTINCT so) AS count
        """)
        r = result.single()
        logger.info(f"   Orders with no delivery:       {r['count']:>6,}")

        # ── Billing docs with no journal entry ───────────────
        result = session.run("""
            MATCH (bd:BillingDocument)
            WHERE NOT (bd)-[:RECORDED_IN]->()
            RETURN count(*) AS count
        """)
        r = result.single()
        logger.info(f"   Billing docs without journal:  {r['count']:>6,}")

        # ── Journal entries not cleared by payment ────────────
        result = session.run("""
            MATCH (je:JournalEntry)
            WHERE NOT (je)-[:CLEARED_BY]->()
            RETURN count(*) AS count
        """)
        r = result.single()
        logger.info(f"   Journal entries not cleared:   {r['count']:>6,}")

        # ── Top 3 products by billing volume ─────────────────
        logger.info("\n🏆 TOP 3 PRODUCTS BY BILLING DOCUMENTS:")
        result = session.run("""
            MATCH (bdi:BillingDocumentItem)-[:FOR_PRODUCT]->(p:Product)
            RETURN p.description AS product,
                   count(bdi)    AS billingCount
            ORDER BY billingCount DESC
            LIMIT 3
        """)
        for r in result:
            desc = r['product'] or 'No description'
            logger.info(f"   {desc[:35]:<35} {r['billingCount']:>4,} billing items")

        # ── Top 3 customers by order value ───────────────────
        logger.info("\n👤 TOP 3 CUSTOMERS BY TOTAL ORDER VALUE:")
        result = session.run("""
            MATCH (bp:BusinessPartner)-[:PLACED]->(so:SalesOrder)
            RETURN bp.fullName                  AS customer,
                   count(so)                    AS orderCount,
                   sum(toFloat(so.totalNetAmount)) AS totalValue
            ORDER BY totalValue DESC
            LIMIT 3
        """)
        for r in result:
            name = r['customer'] or 'Unknown'
            logger.info(
                f"   {name[:30]:<30} "
                f"orders: {r['orderCount']:>3}  "
                f"value: {r['totalValue']:>12,.2f}"
            )

    logger.info("\n" + "=" * 55)
    logger.info("  ✅ Validation complete — graph is ready")
    logger.info("=" * 55 + "\n")