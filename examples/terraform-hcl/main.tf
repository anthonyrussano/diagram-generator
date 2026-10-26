data "aws_ami" "linux" {
  most_recent = true
  owners      = ["amazon"]
}

resource "aws_vpc" "main" {
  cidr_block = "10.42.0.0/16"
}

resource "aws_subnet" "app" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.42.1.0/24"
}

resource "aws_instance" "web" {
  ami           = data.aws_ami.linux.id
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.app.id
  depends_on    = [aws_vpc.main]
}
