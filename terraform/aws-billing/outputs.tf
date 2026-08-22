output "account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "user_arn" {
  value = aws_iam_user.billing_reader.arn
}

output "access_key_id" {
  value = aws_iam_access_key.billing_reader.id
}

output "secret_access_key" {
  value     = aws_iam_access_key.billing_reader.secret
  sensitive = true
}
