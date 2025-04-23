# Use an official Python runtime as the base image
FROM python:3.11.7-slim

RUN rm -rf /homelabids
# Install system packages
RUN apt-get update && apt-get install -y \
    git \
    supervisor \
    nmap \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Clone the repository
RUN git clone https://github.com/mayberryjp/homelabids.git /homelabids

# Set the working directory
WORKDIR /homelabids

RUN pip install schedule requests bottle dnspython python-nmap

# Expose the port
EXPOSE 2055
EXPOSE 8044

ENV PYTHONUNBUFFERED=1

# Run the app
ENTRYPOINT ["/usr/bin/supervisord", "-c", "/homelabids/super.conf"]
CMD ["-n"]