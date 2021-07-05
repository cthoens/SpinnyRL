import socket
import sys
import os

from gpiozero import LED
import time

class StepperMotor:

    def __init__(self, A1, A2, B1, B2):
        self.PIN_A1 = LED( A1 )
        self.PIN_A2 = LED( A2 )
        self.PIN_B1 = LED( B1 )
        self.PIN_B2 = LED( B2 )

    def forward(self, delay, steps):
        for i in range(0, steps):
            self.setStep(1, 0, 1, 0)
            time.sleep(delay)
            self.setStep(0, 1, 1, 0)
            time.sleep(delay)
            self.setStep(0, 1, 0, 1)
            time.sleep(delay)
            self.setStep(1, 0, 0, 1)
            time.sleep(delay)

    def backward(self, delay, steps):
        for i in range(0, steps):
            self.setStep(1, 0, 0, 1)
            time.sleep(delay)
            self.setStep(0, 1, 0, 1)
            time.sleep(delay)
            self.setStep(0, 1, 1, 0)
            time.sleep(delay)
            self.setStep(1, 0, 1, 0)
            time.sleep(delay)

    def setStep(self, w1, w2, w3, w4):
        self.PIN_A1.value = w1
        self.PIN_A2.value = w2
        self.PIN_B1.value = w3
        self.PIN_B2.value = w4


def main():
	server_address = '/tmp/uv4l.socket'

	# Make sure the socket does not already exist
	try:
	    os.unlink(server_address)
	except OSError:
		if os.path.exists(server_address):
			raise


	# Create a UDS socket
	sock = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)

	# Bind the socket to the port
	print('starting up on %s' % server_address)
	sock.bind(server_address)

	# Listen for incoming connections
	sock.listen(1)
	
	motor1 = StepperMotor(2, 15, 3, 18)

	while True:
		# Wait for a connection
		print('waiting for a connection')
		connection, client_address = sock.accept()
		try:
			print('connection from', client_address)

			# Receive the data in small chunks and retransmit it
			while True:
				data = connection.recv(16)
				if data:
					step_count = int.from_bytes(data, byteorder="big", signed=True)
					if step_count >= 0:
						motor1.forward(5.0/1000, step_count)
					else:
						motor1.backward(5.0/1000, -step_count)
				else:
					print('no more data from', client_address)
					break				
		    
		finally:
			# Clean up the connection
			connection.close()

if __name__=="__main__":
	main()
