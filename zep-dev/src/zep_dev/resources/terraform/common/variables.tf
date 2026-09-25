variable "namespace" {
  type = string

  validation {
    condition     = length(var.namespace) > 0
    error_message = "namespace must not be empty."
  }
}
