
output "vector_search_collection_id" {
  description = "Vector Search collection ID"
  value       = var.vector_search_collection_id
}

output "pipeline_gcs_bucket_name" {
  description = "Pipeline GCS bucket name"
  value       = google_storage_bucket.data_ingestion_PIPELINE_GCS_ROOT.name
}

