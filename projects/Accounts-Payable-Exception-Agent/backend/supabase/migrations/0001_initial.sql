-- Accounts Payable Exception Agent — initial schema for Supabase/PostgreSQL.
-- Generated from backend/app/models.py (SQLAlchemy metadata, postgresql dialect).
-- Regenerate after model changes with:
--   cd backend && .venv/bin/python -m scripts.export_schema > supabase/migrations/0001_initial.sql
--
-- The API connects with the service role / database owner and enforces tenancy
-- in application code (every query is scoped by organization membership).
-- Row Level Security is enabled below so that anon/authenticated roles using
-- the Supabase client directly cannot read these tables at all.


CREATE TABLE organizations (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	slug VARCHAR(100) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (slug)
);

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	display_name VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE memberships (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, user_id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_memberships_organization_id ON memberships (organization_id);

CREATE INDEX ix_memberships_user_id ON memberships (user_id);

CREATE TABLE vendors (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	vendor_code VARCHAR(64) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	normalized_name VARCHAR(200) NOT NULL, 
	tax_id VARCHAR(64), 
	status VARCHAR(32) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, vendor_code), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_vendors_organization_id ON vendors (organization_id);

CREATE INDEX ix_vendors_normalized_name ON vendors (normalized_name);

CREATE TABLE beneficiaries (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	vendor_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	account_name VARCHAR(200) NOT NULL, 
	sort_code VARCHAR(16), 
	account_number VARCHAR(34), 
	iban VARCHAR(40), 
	verification_status VARCHAR(32) NOT NULL, 
	verification_note TEXT, 
	verified_by VARCHAR(36), 
	verified_at TIMESTAMP WITH TIME ZONE, 
	is_current BOOLEAN NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (vendor_id, version), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(vendor_id) REFERENCES vendors (id), 
	FOREIGN KEY(verified_by) REFERENCES users (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_beneficiaries_vendor_id ON beneficiaries (vendor_id);

CREATE INDEX ix_beneficiaries_organization_id ON beneficiaries (organization_id);

CREATE TABLE cases (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	reference VARCHAR(64) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	assigned_to VARCHAR(36), 
	invoice_number VARCHAR(100), 
	supplier_name VARCHAR(200), 
	amount_minor INTEGER, 
	currency VARCHAR(3) NOT NULL, 
	vendor_id VARCHAR(36), 
	beneficiary_id VARCHAR(36), 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, reference), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(created_by) REFERENCES users (id), 
	FOREIGN KEY(assigned_to) REFERENCES users (id), 
	FOREIGN KEY(vendor_id) REFERENCES vendors (id), 
	FOREIGN KEY(beneficiary_id) REFERENCES beneficiaries (id)
);

CREATE INDEX ix_cases_organization_id ON cases (organization_id);

CREATE INDEX ix_cases_invoice_number ON cases (invoice_number);

CREATE INDEX ix_cases_status ON cases (status);

CREATE TABLE agent_runs (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	thread_id VARCHAR(100) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	started_by VARCHAR(36) NOT NULL, 
	model_name VARCHAR(100), 
	prompt_version VARCHAR(64), 
	model_calls INTEGER NOT NULL, 
	tool_calls INTEGER NOT NULL, 
	trace JSON NOT NULL, 
	summary TEXT, 
	outcome VARCHAR(64), 
	pending_resume JSON, 
	error TEXT, 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(started_by) REFERENCES users (id)
);

CREATE INDEX ix_agent_runs_thread_id ON agent_runs (thread_id);

CREATE INDEX ix_agent_runs_organization_id ON agent_runs (organization_id);

CREATE INDEX ix_agent_runs_case_id ON agent_runs (case_id);

CREATE TABLE approval_requests (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	snapshot JSON NOT NULL, 
	policy_version VARCHAR(64) NOT NULL, 
	requested_by VARCHAR(36) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	invalidation_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_approval_requests_organization_id ON approval_requests (organization_id);

CREATE INDEX ix_approval_requests_snapshot_hash ON approval_requests (snapshot_hash);

CREATE INDEX ix_approval_requests_case_id ON approval_requests (case_id);

CREATE TABLE audit_events (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36), 
	actor_type VARCHAR(16) NOT NULL, 
	actor_id VARCHAR(36), 
	event_type VARCHAR(64) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_audit_events_case_id ON audit_events (case_id);

CREATE INDEX ix_audit_events_case_created ON audit_events (case_id, created_at);

CREATE INDEX ix_audit_events_organization_id ON audit_events (organization_id);

CREATE INDEX ix_audit_events_event_type ON audit_events (event_type);

CREATE TABLE case_comments (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	author_id VARCHAR(36) NOT NULL, 
	body TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(author_id) REFERENCES users (id)
);

CREATE INDEX ix_case_comments_organization_id ON case_comments (organization_id);

CREATE INDEX ix_case_comments_case_id ON case_comments (case_id);

CREATE TABLE document_versions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	document_id VARCHAR(36) NOT NULL, 
	version INTEGER NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	content_type VARCHAR(100) NOT NULL, 
	storage_key VARCHAR(500) NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	size_bytes INTEGER NOT NULL, 
	page_count INTEGER NOT NULL, 
	text_pages JSON, 
	is_current BOOLEAN NOT NULL, 
	uploaded_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (document_id, version), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(uploaded_by) REFERENCES users (id)
);

CREATE INDEX ix_document_versions_sha256 ON document_versions (sha256);

CREATE INDEX ix_document_versions_case_kind ON document_versions (case_id, kind);

CREATE INDEX ix_document_versions_case_id ON document_versions (case_id);

CREATE INDEX ix_document_versions_organization_id ON document_versions (organization_id);

CREATE INDEX ix_document_versions_document_id ON document_versions (document_id);

CREATE TABLE approval_decisions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	approval_request_id VARCHAR(36) NOT NULL, 
	decided_by VARCHAR(36) NOT NULL, 
	decision VARCHAR(16) NOT NULL, 
	note TEXT, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(approval_request_id) REFERENCES approval_requests (id), 
	FOREIGN KEY(decided_by) REFERENCES users (id)
);

CREATE INDEX ix_approval_decisions_approval_request_id ON approval_decisions (approval_request_id);

CREATE INDEX ix_approval_decisions_organization_id ON approval_decisions (organization_id);

CREATE TABLE clarification_drafts (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	agent_run_id VARCHAR(36), 
	recipient VARCHAR(200) NOT NULL, 
	subject VARCHAR(300) NOT NULL, 
	body TEXT NOT NULL, 
	requested_items JSON, 
	status VARCHAR(32) NOT NULL, 
	authored_by VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id)
);

CREATE INDEX ix_clarification_drafts_case_id ON clarification_drafts (case_id);

CREATE INDEX ix_clarification_drafts_organization_id ON clarification_drafts (organization_id);

CREATE TABLE exceptions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	code VARCHAR(64) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	detail TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	needs_information BOOLEAN NOT NULL, 
	detected_by VARCHAR(32) NOT NULL, 
	agent_run_id VARCHAR(36), 
	resolution_note TEXT, 
	resolved_by VARCHAR(36), 
	resolved_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(agent_run_id) REFERENCES agent_runs (id), 
	FOREIGN KEY(resolved_by) REFERENCES users (id)
);

CREATE INDEX ix_exceptions_code ON exceptions (code);

CREATE INDEX ix_exceptions_case_id ON exceptions (case_id);

CREATE INDEX ix_exceptions_organization_id ON exceptions (organization_id);

CREATE TABLE extracted_fields (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	document_version_id VARCHAR(36) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	value_text TEXT, 
	value_json JSON, 
	page INTEGER, 
	excerpt TEXT, 
	confidence DOUBLE PRECISION, 
	source VARCHAR(32) NOT NULL, 
	revision INTEGER NOT NULL, 
	created_by VARCHAR(36), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(document_version_id) REFERENCES document_versions (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_extracted_fields_document_version_id ON extracted_fields (document_version_id);

CREATE INDEX ix_extracted_fields_organization_id ON extracted_fields (organization_id);

CREATE INDEX ix_extracted_fields_doc_name ON extracted_fields (document_version_id, name);

CREATE TABLE payment_instructions (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	approval_request_id VARCHAR(36) NOT NULL, 
	snapshot_hash VARCHAR(64) NOT NULL, 
	audit_reference VARCHAR(64) NOT NULL, 
	instruction JSON NOT NULL, 
	summary_text TEXT NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (approval_request_id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(approval_request_id) REFERENCES approval_requests (id), 
	UNIQUE (audit_reference), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_payment_instructions_case_id ON payment_instructions (case_id);

CREATE INDEX ix_payment_instructions_organization_id ON payment_instructions (organization_id);

CREATE TABLE evidence_links (
	id VARCHAR(36) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	case_id VARCHAR(36) NOT NULL, 
	exception_id VARCHAR(36), 
	document_version_id VARCHAR(36), 
	record_type VARCHAR(64), 
	record_id VARCHAR(36), 
	page INTEGER, 
	excerpt TEXT, 
	label VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id), 
	FOREIGN KEY(case_id) REFERENCES cases (id), 
	FOREIGN KEY(exception_id) REFERENCES exceptions (id), 
	FOREIGN KEY(document_version_id) REFERENCES document_versions (id)
);

CREATE INDEX ix_evidence_links_organization_id ON evidence_links (organization_id);

CREATE INDEX ix_evidence_links_case_id ON evidence_links (case_id);

CREATE INDEX ix_evidence_links_exception_id ON evidence_links (exception_id);

-- Deny direct access from browser roles; only the API (service role) reads/writes.

ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

ALTER TABLE users ENABLE ROW LEVEL SECURITY;

ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;

ALTER TABLE vendors ENABLE ROW LEVEL SECURITY;

ALTER TABLE beneficiaries ENABLE ROW LEVEL SECURITY;

ALTER TABLE cases ENABLE ROW LEVEL SECURITY;

ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE case_comments ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_versions ENABLE ROW LEVEL SECURITY;

ALTER TABLE approval_decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE clarification_drafts ENABLE ROW LEVEL SECURITY;

ALTER TABLE exceptions ENABLE ROW LEVEL SECURITY;

ALTER TABLE extracted_fields ENABLE ROW LEVEL SECURITY;

ALTER TABLE payment_instructions ENABLE ROW LEVEL SECURITY;

ALTER TABLE evidence_links ENABLE ROW LEVEL SECURITY;
