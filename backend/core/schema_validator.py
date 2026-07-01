from pymongo.errors import OperationFailure, CollectionInvalid
from core.auth import db

COLLECTION_SCHEMAS = {
    "tenants": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "api_key", "api_key_hash", "domain", "business_name", "email", "password_hash", "created_at", "status"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "api_key": {"bsonType": "string"},
                    "api_key_hash": {"bsonType": "string"},
                    "domain": {"bsonType": "string"},
                    "business_name": {"bsonType": "string"},
                    "email": {"bsonType": "string"},
                    "password_hash": {"bsonType": "string"},
                    "plan": {"bsonType": "string"},
                    "theme": {"bsonType": "string"},
                    "description": {"bsonType": ["string", "null"]},
                    "suggested_questions_manual": {"bsonType": "array", "items": {"bsonType": "string"}},
                    "suggested_questions_auto": {"bsonType": "array", "items": {"bsonType": "string"}},
                    "show_sources": {"bsonType": "bool"},
                    "created_at": {"bsonType": "date"},
                    "status": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "sources": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "source_type", "name", "config", "status", "created_at", "updated_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "source_type": {"enum": ["pdf", "faq", "text", "website"]},
                    "name": {"bsonType": "string"},
                    "config": {"bsonType": "object"},
                    "status": {"enum": ["ready", "indexing", "failed"]},
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                    "last_indexed_at": {"bsonType": ["date", "null"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "crawl_jobs": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "job_id", "seed_url", "status", "pages_found", "chunks_created", "embedding_errors"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "job_id": {"bsonType": "string"},
                    "seed_url": {"bsonType": "string"},
                    "status": {"enum": ["queued", "running", "done", "failed", "purged"]},
                    "pages_found": {"bsonType": "int"},
                    "chunks_created": {"bsonType": "int"},
                    "embedding_errors": {"bsonType": "int"},
                    "started_at": {"bsonType": ["date", "null"]},
                    "finished_at": {"bsonType": ["date", "null"]},
                    "error": {"bsonType": ["string", "null"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "source_jobs": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "job_id", "source_id", "job_type", "status", "chunks_created", "embedding_errors", "config", "created_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "job_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "job_type": {"enum": ["crawl", "pdf_index", "faq_index", "text_index"]},
                    "status": {"enum": ["queued", "running", "done", "failed", "purged"]},
                    "chunks_created": {"bsonType": "int"},
                    "embedding_errors": {"bsonType": "int"},
                    "pages_found": {"bsonType": "int"},
                    "started_at": {"bsonType": ["date", "null"]},
                    "finished_at": {"bsonType": ["date", "null"]},
                    "error": {"bsonType": ["string", "null"]},
                    "config": {"bsonType": "object"},
                    "created_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "faqs": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "faq_id", "question", "answer", "created_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "faq_id": {"bsonType": "string"},
                    "question": {"bsonType": "string"},
                    "answer": {"bsonType": "string"},
                    "created_at": {"bsonType": "date"},
                    "embedding": {"bsonType": ["array", "null"], "items": {"bsonType": "double"}},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "documents": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "doc_id", "title", "body", "created_at", "updated_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "doc_id": {"bsonType": "string"},
                    "title": {"bsonType": "string"},
                    "body": {"bsonType": "string"},
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "chunks": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "page_id", "parent_id", "url", "title", "text", "token_count", "embedding", "chunk_index", "parent_index", "child_index", "indexed_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "page_id": {"bsonType": "string"},
                    "parent_id": {"bsonType": "string"},
                    "url": {"bsonType": "string"},
                    "title": {"bsonType": "string"},
                    "section_title": {"bsonType": "string"},
                    "section_path": {"bsonType": "string"},
                    "headings": {"bsonType": "object"},
                    "text": {"bsonType": "string"},
                    "token_count": {"bsonType": "int"},
                    "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
                    "chunk_index": {"bsonType": "int"},
                    "parent_index": {"bsonType": "int"},
                    "child_index": {"bsonType": "int"},
                    "indexed_at": {"bsonType": "date"},
                    "crawl_id": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "parents": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "page_id", "parent_id", "url", "title", "text", "token_count", "parent_index", "indexed_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "page_id": {"bsonType": "string"},
                    "parent_id": {"bsonType": "string"},
                    "url": {"bsonType": "string"},
                    "title": {"bsonType": "string"},
                    "section_title": {"bsonType": "string"},
                    "section_path": {"bsonType": "string"},
                    "headings": {"bsonType": "object"},
                    "text": {"bsonType": "string"},
                    "token_count": {"bsonType": "int"},
                    "parent_index": {"bsonType": "int"},
                    "indexed_at": {"bsonType": "date"},
                    "crawl_id": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "pages": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "source_id", "page_id", "url", "title", "content", "indexed_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "source_id": {"bsonType": "string"},
                    "page_id": {"bsonType": "string"},
                    "url": {"bsonType": "string"},
                    "title": {"bsonType": "string"},
                    "content": {"bsonType": "string"},
                    "indexed_at": {"bsonType": "date"},
                    "crawl_id": {"bsonType": "string"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "leads": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["lead_id", "tenant_id", "session_id", "name", "email", "phone", "message", "raw_context", "source_url", "created_at"],
                "properties": {
                    "lead_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "session_id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "email": {"bsonType": "string"},
                    "phone": {"bsonType": "string"},
                    "message": {"bsonType": "string"},
                    "raw_context": {"bsonType": "string"},
                    "source_url": {"bsonType": "string"},
                    "form_id": {"bsonType": ["string", "null"]},
                    "custom_fields": {"bsonType": ["object", "null"]},
                    "visitor_id": {"bsonType": ["string", "null"]},
                    "created_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "conversations": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["session_id", "tenant_id", "current_url", "summary", "messages"],
                "properties": {
                    "session_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "current_url": {"bsonType": "string"},
                    "summary": {"bsonType": "string"},
                    "created_at": {"bsonType": ["date", "null"]},
                    "updated_at": {"bsonType": ["date", "null"]},
                    "messages": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["role", "content"],
                            "properties": {
                                "role": {"enum": ["user", "assistant"]},
                                "content": {"bsonType": "string"},
                            },
                        },
                    },
                    "archived": {"bsonType": "bool"},
                    "archive_key": {"bsonType": ["string", "null"]},
                    "archived_turn_count": {"bsonType": "int"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "visitors": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["session_id", "tenant_id", "conversation_ids", "total_messages"],
                "properties": {
                    "session_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "first_seen_at": {"bsonType": "date"},
                    "last_seen_at": {"bsonType": "date"},
                    "conversation_ids": {"bsonType": "array", "items": {"bsonType": "string"}},
                    "total_messages": {"bsonType": "int"},
                    "ip_history": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["ip", "seen_at"],
                            "properties": {
                                "ip": {"bsonType": "string"},
                                "seen_at": {"bsonType": "date"},
                            },
                        },
                    },
                    "page_views": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["url", "title", "timestamp"],
                            "properties": {
                                "url": {"bsonType": "string"},
                                "title": {"bsonType": "string"},
                                "timestamp": {"bsonType": "date"},
                            },
                        },
                    },
                    "profile_id": {"bsonType": ["string", "null"]},
                    "profile_label": {"bsonType": ["string", "null"]},
                    "profile_confidence": {"bsonType": ["double", "null"]},
                    "profile_history": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["profile_id", "profile_label", "assigned_at", "reason", "source"],
                            "properties": {
                                "profile_id": {"bsonType": "string"},
                                "profile_label": {"bsonType": "string"},
                                "assigned_at": {"bsonType": "date"},
                                "reason": {"bsonType": "string"},
                                "source": {"enum": ["rule", "llm"]},
                            },
                        },
                    },
                    "last_classified_at": {"bsonType": ["date", "null"]},
                    "identity": {
                        "bsonType": "object",
                        "properties": {
                            "name": {"bsonType": ["string", "null"]},
                            "email": {"bsonType": ["string", "null"]},
                            "phone": {"bsonType": ["string", "null"]},
                            "updated_at": {"bsonType": ["date", "null"]},
                            "source_lead_id": {"bsonType": ["string", "null"]},
                        },
                    },
                    "utm_source": {"bsonType": ["string", "null"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "message_feedback": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "session_id", "message_id", "rating", "created_at"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "session_id": {"bsonType": "string"},
                    "message_id": {"bsonType": "string"},
                    "rating": {"enum": ["like", "dislike"]},
                    "created_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "lead_form_configs": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["form_id", "tenant_id", "title", "fields", "trigger_instructions", "enabled", "created_at", "updated_at"],
                "properties": {
                    "form_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "title": {"bsonType": "string"},
                    "fields": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["field_id", "label", "type", "required", "order"],
                            "properties": {
                                "field_id": {"bsonType": "string"},
                                "label": {"bsonType": "string"},
                                "type": {"enum": ["text", "email", "phone", "textarea", "select", "checkbox"]},
                                "required": {"bsonType": "bool"},
                                "placeholder": {"bsonType": ["string", "null"]},
                                "options": {"bsonType": ["array", "null"], "items": {"bsonType": "string"}},
                                "order": {"bsonType": "int"},
                                "field_role": {"bsonType": ["string", "null"], "enum": ["name", "email", "phone", None]},
                            },
                        },
                    },
                    "trigger_instructions": {"bsonType": "string"},
                    "enabled": {"bsonType": "bool"},
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "visitor_profiles": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["profile_id", "tenant_id", "name", "description", "color", "rules", "enabled", "created_at", "updated_at"],
                "properties": {
                    "profile_id": {"bsonType": "string"},
                    "tenant_id": {"bsonType": "string"},
                    "name": {"bsonType": "string"},
                    "description": {"bsonType": "string"},
                    "color": {"bsonType": "string"},
                    "rules": {
                        "bsonType": "array",
                        "items": {
                            "bsonType": "object",
                            "required": ["type"],
                            "properties": {
                                "type": {"enum": ["page_visited", "lead_form_field", "message_count_gte", "keyword_match", "utm_source"]},
                                "priority": {"bsonType": "int"},
                            },
                        },
                    },
                    "llm_criteria": {"bsonType": ["string", "null"]},
                    "enabled": {"bsonType": "bool"},
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
    "knowledge_gaps": {
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["tenant_id", "query", "url", "gap_type", "message_id", "embedding", "count", "status", "first_seen", "last_seen"],
                "properties": {
                    "tenant_id": {"bsonType": "string"},
                    "query": {"bsonType": "string"},
                    "url": {"bsonType": "string"},
                    "gap_type": {"enum": ["knowledge_gap", "out_of_scope", "no_context"]},
                    "message_id": {"bsonType": "string"},
                    "embedding": {"bsonType": "array", "items": {"bsonType": "double"}},
                    "count": {"bsonType": "int"},
                    "status": {"enum": ["open", "resolved", "dismissed"]},
                    "resolved_by_faq_id": {"bsonType": ["string", "null"]},
                    "cluster_id": {"bsonType": ["string", "null"]},
                    "first_seen": {"bsonType": "date"},
                    "last_seen": {"bsonType": "date"},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    },
}


async def ensure_schemas():
    """Apply JSON Schema validators to all collections.
    
    Creates collections if they don't exist, alters them if they do.
    """
    for coll_name, opts in COLLECTION_SCHEMAS.items():
        try:
            await db.create_collection(coll_name, **opts)
            print(f"[SCHEMA] Created collection '{coll_name}' with validator")
        except CollectionInvalid:
            try:
                await db.command("collMod", coll_name, **opts)
                print(f"[SCHEMA] Updated validator for existing collection '{coll_name}'")
            except OperationFailure as mod_err:
                print(f"[SCHEMA] Could not modify collection '{coll_name}': {mod_err}")
