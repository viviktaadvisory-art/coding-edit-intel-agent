terraform {
  backend "gcs" {
    bucket = "codingeditintelligence-terraform-state"
    prefix = "coding-edit-intel-agent/dev"
  }
}
