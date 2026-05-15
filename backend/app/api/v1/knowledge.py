from fastapi import APIRouter, Depends, Request
from app.api.v1.auth import get_current_user
from app.models.user import User

router = APIRouter()


@router.get("/knowledge/graph")
async def get_knowledge_graph(
    request: Request,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
):
    """Return nodes and edges for D3 visualization."""
    neo4j = request.app.state.neo4j
    
    # Get nodes
    nodes_result = await neo4j.execute(
        "MATCH (n:Entity {source: 'ownthink'}) "
        "RETURN n.name AS name, n.描述 AS desc, n.标签 AS tag "
        "LIMIT $limit",
        limit=limit,
    )
    nodes = [
        {"id": r["name"], "name": r["name"], "desc": r.get("desc", ""), "tag": r.get("tag", "")}
        for r in nodes_result
    ]

    # Get edges (Entity -> Entity relationships)
    names = [n["name"] for n in nodes]
    edges_result = await neo4j.execute(
        "MATCH (a:Entity)-[r]->(b:Entity) "
        "WHERE a.name IN $names AND b.name IN $names "
        "RETURN a.name AS source, b.name AS target, type(r) AS rel_type "
        "LIMIT 500",
        names=names,
    )
    edges = [
        {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
        for r in edges_result
    ]
    
    # Get tag edges (Entity -> TagCategory)
    tag_edges_result = await neo4j.execute(
        "MATCH (a:Entity)-[r:TAG]->(t:TagCategory) "
        "WHERE a.name IN $names "
        "RETURN a.name AS source, t.name AS target, type(r) AS rel_type "
        "LIMIT 500",
        names=names,
    )
    edges.extend([
        {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
        for r in tag_edges_result
    ])
    
    # Get dynasty edges (Entity -> Dynasty)
    dynasty_edges_result = await neo4j.execute(
        "MATCH (a:Entity)-[r:BELONGS_TO_DYNASTY]->(d:Dynasty) "
        "WHERE a.name IN $names "
        "RETURN a.name AS source, d.name AS target, type(r) AS rel_type "
        "LIMIT 100",
        names=names,
    )
    edges.extend([
        {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
        for r in dynasty_edges_result
    ])
    
    # Get country edges (Entity -> Country)
    country_edges_result = await neo4j.execute(
        "MATCH (a:Entity)-[r:LOCATED_IN]->(c:Country) "
        "WHERE a.name IN $names "
        "RETURN a.name AS source, c.name AS target, type(r) AS rel_type "
        "LIMIT 100",
        names=names,
    )
    edges.extend([
        {"source": r["source"], "target": r["target"], "type": r["rel_type"]}
        for r in country_edges_result
    ])

    return {"nodes": nodes, "edges": edges}
