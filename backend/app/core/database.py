import logging
from neo4j import GraphDatabase, Driver
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        settings = get_settings()

        logger.info(f"Connecting to Neo4j at {settings.neo4j_uri}")
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
            max_connection_pool_size=50,
            connection_acquisition_timeout=30,
        )
        _driver.verify_connectivity()
        logger.info("Neo4j connection established successfully")

    return _driver


def close_driver() -> None:
    global _driver
    if _driver:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")