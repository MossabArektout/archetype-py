"""Internal database engine details, not meant to be imported outside app.db."""


class Engine:
    def query_one(self, table: str, record_id: int) -> dict:
        return {"table": table, "id": record_id}

    def insert(self, table: str, data: dict) -> dict:
        return {"table": table, **data}
