variable "user_name" {
  type        = string
  default     = "conky-billing-reader"
  description = "IAM user the affine billing map uses for Cost Explorer, Budgets, and CloudWatch billing alarms."
}
