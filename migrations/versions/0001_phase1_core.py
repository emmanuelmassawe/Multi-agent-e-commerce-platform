"""Frozen PostgreSQL schema for the Phase 1 core model."""

from alembic import op

revision = "0001_phase1_core"
down_revision = None
branch_labels = None
depends_on = None

TENANT_TABLES = ('agent_runs', 'carriers', 'customers', 'products', 'suppliers', 'users', 'warehouses', 'api_keys', 'approval_requests', 'audit_logs', 'autonomy_settings', 'competitor_listings', 'conversations', 'inventory_items', 'orders', 'price_rules', 'price_snapshots', 'refresh_tokens', 'token_usage', 'tool_calls', 'messages', 'shipments', 'shipment_events')
DOWNGRADE_TABLES = ('shipment_events', 'shipments', 'messages', 'tool_calls', 'token_usage', 'refresh_tokens', 'price_snapshots', 'price_rules', 'orders', 'inventory_items', 'conversations', 'competitor_listings', 'autonomy_settings', 'audit_logs', 'approval_requests', 'api_keys', 'warehouses', 'users', 'suppliers', 'products', 'customers', 'carriers', 'agent_runs', 'tenants')
UPGRADE_SQL = (
    'CREATE TABLE tenants (\n\tid UUID NOT NULL, \n\tslug VARCHAR(80) NOT NULL, \n\tname VARCHAR(200) NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_tenants_slug UNIQUE (slug)\n)',
    'CREATE TABLE agent_runs (\n\tagent_name VARCHAR(80) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tautonomy_mode VARCHAR(24) NOT NULL, \n\texplanation JSON, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_agent_runs_tenant_id ON agent_runs (tenant_id)',
    'CREATE TABLE carriers (\n\tname VARCHAR(120) NOT NULL, \n\tsupported_regions JSON NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_carriers_tenant_name UNIQUE (tenant_id, name), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_carriers_tenant_id ON carriers (tenant_id)',
    'CREATE TABLE customers (\n\tdisplay_name VARCHAR(200) NOT NULL, \n\temail VARCHAR(320), \n\tphone VARCHAR(40), \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_customers_tenant_id ON customers (tenant_id)',
    'CREATE TABLE products (\n\tsku VARCHAR(100) NOT NULL, \n\tname VARCHAR(240) NOT NULL, \n\tdescription TEXT, \n\tcurrency VARCHAR(3) NOT NULL, \n\tactive BOOLEAN NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_products_tenant_sku UNIQUE (tenant_id, sku), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_products_tenant_id ON products (tenant_id)',
    'CREATE TABLE suppliers (\n\tname VARCHAR(200) NOT NULL, \n\tcontact_email VARCHAR(320), \n\tlead_time_days INTEGER, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_suppliers_tenant_id ON suppliers (tenant_id)',
    'CREATE TABLE users (\n\temail VARCHAR(320) NOT NULL, \n\tfull_name VARCHAR(200) NOT NULL, \n\tpassword_hash VARCHAR(512) NOT NULL, \n\trole VARCHAR(32) NOT NULL, \n\tis_active BOOLEAN NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_users_tenant_id ON users (tenant_id)',
    'CREATE TABLE warehouses (\n\tname VARCHAR(200) NOT NULL, \n\tregion VARCHAR(100) NOT NULL, \n\ttimezone VARCHAR(64) NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_warehouses_tenant_id ON warehouses (tenant_id)',
    'CREATE TABLE api_keys (\n\tuser_id UUID NOT NULL, \n\tlabel VARCHAR(120) NOT NULL, \n\tprefix VARCHAR(16) NOT NULL, \n\tkey_hash VARCHAR(64) NOT NULL, \n\tpermissions JSON NOT NULL, \n\tidempotency_key VARCHAR(200) NOT NULL, \n\trequest_hash VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE, \n\tlast_used_at TIMESTAMP WITH TIME ZONE, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash), \n\tCONSTRAINT uq_api_keys_idempotency UNIQUE (tenant_id, idempotency_key), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_api_keys_prefix ON api_keys (prefix)',
    'CREATE INDEX ix_api_keys_tenant_id ON api_keys (tenant_id)',
    'CREATE TABLE approval_requests (\n\tagent_run_id UUID NOT NULL, \n\taction VARCHAR(160) NOT NULL, \n\trisk_level VARCHAR(24) NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\tcontext JSON NOT NULL, \n\trequested_by UUID, \n\tdecided_by UUID, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tdecided_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(agent_run_id) REFERENCES agent_runs (id), \n\tFOREIGN KEY(requested_by) REFERENCES users (id), \n\tFOREIGN KEY(decided_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_approval_requests_tenant_id ON approval_requests (tenant_id)',
    'CREATE TABLE audit_logs (\n\tactor_id UUID, \n\taction VARCHAR(120) NOT NULL, \n\tentity_type VARCHAR(120) NOT NULL, \n\tentity_id UUID, \n\tdetails JSON NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(actor_id) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_audit_logs_tenant_created ON audit_logs (tenant_id, created_at)',
    'CREATE INDEX ix_audit_logs_tenant_id ON audit_logs (tenant_id)',
    'CREATE TABLE autonomy_settings (\n\tagent_name VARCHAR(80) NOT NULL, \n\tmode VARCHAR(24) NOT NULL, \n\tupdated_by UUID, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_autonomy_tenant_agent UNIQUE (tenant_id, agent_name), \n\tFOREIGN KEY(updated_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_autonomy_settings_tenant_id ON autonomy_settings (tenant_id)',
    'CREATE TABLE competitor_listings (\n\tproduct_id UUID NOT NULL, \n\tsource VARCHAR(120) NOT NULL, \n\texternal_ref VARCHAR(240), \n\tprice NUMERIC(18, 4) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tobserved_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_competitor_listings_tenant_id ON competitor_listings (tenant_id)',
    'CREATE TABLE conversations (\n\tcustomer_id UUID NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_conversations_tenant_id ON conversations (tenant_id)',
    'CREATE TABLE inventory_items (\n\tproduct_id UUID NOT NULL, \n\twarehouse_id UUID NOT NULL, \n\tquantity INTEGER NOT NULL, \n\treserved_quantity INTEGER NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_inventory_product_warehouse UNIQUE (tenant_id, product_id, warehouse_id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(warehouse_id) REFERENCES warehouses (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_inventory_items_tenant_id ON inventory_items (tenant_id)',
    'CREATE INDEX ix_inventory_tenant_product ON inventory_items (tenant_id, product_id)',
    'CREATE TABLE orders (\n\texternal_ref VARCHAR(120), \n\tcustomer_id UUID, \n\tstatus VARCHAR(32) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\ttotal NUMERIC(18, 4) NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_orders_tenant_external_ref UNIQUE (tenant_id, external_ref), \n\tFOREIGN KEY(customer_id) REFERENCES customers (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_orders_tenant_id ON orders (tenant_id)',
    'CREATE TABLE price_rules (\n\tproduct_id UUID NOT NULL, \n\tmin_price NUMERIC(18, 4) NOT NULL, \n\tmax_price NUMERIC(18, 4) NOT NULL, \n\tmin_margin NUMERIC(8, 5) NOT NULL, \n\tmax_change_per_day NUMERIC(8, 5), \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_price_rules_tenant_id ON price_rules (tenant_id)',
    'CREATE TABLE price_snapshots (\n\tproduct_id UUID NOT NULL, \n\tprice NUMERIC(18, 4) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\tsource VARCHAR(80) NOT NULL, \n\tobserved_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(product_id) REFERENCES products (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_price_snapshots_tenant_id ON price_snapshots (tenant_id)',
    'CREATE INDEX ix_price_snapshots_tenant_product ON price_snapshots (tenant_id, product_id)',
    'CREATE TABLE refresh_tokens (\n\tuser_id UUID NOT NULL, \n\ttoken_hash VARCHAR(64) NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\trevoked_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT uq_refresh_tokens_hash UNIQUE (token_hash), \n\tFOREIGN KEY(user_id) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_refresh_tokens_tenant_id ON refresh_tokens (tenant_id)',
    'CREATE TABLE token_usage (\n\tagent_run_id UUID NOT NULL, \n\tmodel VARCHAR(120) NOT NULL, \n\tinput_tokens INTEGER NOT NULL, \n\toutput_tokens INTEGER NOT NULL, \n\tcost_usd NUMERIC(18, 8), \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(agent_run_id) REFERENCES agent_runs (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_token_usage_tenant_id ON token_usage (tenant_id)',
    'CREATE TABLE tool_calls (\n\tagent_run_id UUID NOT NULL, \n\ttool_name VARCHAR(120) NOT NULL, \n\tstatus VARCHAR(32) NOT NULL, \n\trisk_level VARCHAR(24) NOT NULL, \n\tidempotency_key VARCHAR(160) NOT NULL, \n\tinput_data JSON NOT NULL, \n\toutput_data JSON, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(agent_run_id) REFERENCES agent_runs (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_tool_calls_tenant_id ON tool_calls (tenant_id)',
    'CREATE TABLE messages (\n\tconversation_id UUID NOT NULL, \n\tdirection VARCHAR(16) NOT NULL, \n\tbody TEXT NOT NULL, \n\tcreated_by UUID, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(conversation_id) REFERENCES conversations (id), \n\tFOREIGN KEY(created_by) REFERENCES users (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_messages_tenant_conversation ON messages (tenant_id, conversation_id)',
    'CREATE INDEX ix_messages_tenant_id ON messages (tenant_id)',
    'CREATE TABLE shipments (\n\torder_id UUID NOT NULL, \n\tcarrier_id UUID, \n\ttracking_number VARCHAR(160), \n\tstatus VARCHAR(32) NOT NULL, \n\tpromised_at TIMESTAMP WITH TIME ZONE, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(order_id) REFERENCES orders (id), \n\tFOREIGN KEY(carrier_id) REFERENCES carriers (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_shipments_tenant_id ON shipments (tenant_id)',
    'CREATE TABLE shipment_events (\n\tshipment_id UUID NOT NULL, \n\tevent_type VARCHAR(80) NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tpayload JSON NOT NULL, \n\tid UUID NOT NULL, \n\ttenant_id UUID NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(shipment_id) REFERENCES shipments (id), \n\tFOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE\n)',
    'CREATE INDEX ix_shipment_events_tenant_id ON shipment_events (tenant_id)',
    'CREATE INDEX ix_shipment_events_tenant_shipment ON shipment_events (tenant_id, shipment_id)',
)


def upgrade() -> None:
    for statement in UPGRADE_SQL:
        op.execute(statement)
    for table in TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"CREATE POLICY tenant_isolation ON \"{table}\" "
            "USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"
        )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO clos_app"
    )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    for table in DOWNGRADE_TABLES:
        op.execute(f'DROP TABLE "{table}"')
