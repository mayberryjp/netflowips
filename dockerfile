# Use an official Python runtime as the base image
FROM python:3.11.7-slim

RUN rm -rf /homelabids
# Install system packages
RUN apt-get update && apt-get install -y \
    git \
    supervisor \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/mayberryjp/homelabids.git /homelabids

# Set the working directory
WORKDIR /homelabids

RUN pip install schedule requests

# Expose the port
EXPOSE 2055

ENV PYTHONUNBUFFERED=1

# Run the app
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/homelabids/super.conf"]
CMD ["-n"]