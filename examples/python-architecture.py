"""Trusted Python authoring: loops, a helper, clusters, and custom edges."""

from diagrams import Cluster, Diagram, Edge
from diagrams.onprem.client import Users
from diagrams.onprem.compute import Server
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.network import Nginx


def worker_pool(count: int):
    return [Server(f"worker {index + 1}") for index in range(count)]


with Diagram("Python-authored worker service", direction="LR"):
    users = Users("Users")
    gateway = Nginx("Gateway")
    with Cluster("Application"):
        workers = worker_pool(3)
    database = PostgreSQL("Database")
    users >> Edge(label="HTTPS") >> gateway
    gateway >> workers
    for worker in workers:
        worker >> Edge(label="queries", color="#2563eb") >> database
