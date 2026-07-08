CC=nvcc
CFLAGS=-O3 -arch=sm_70

all: kernel

kernel: kernel.cu aux.cuh
	$(CC) $(CFLAGS) -o kernel kernel.cu

clean:
	rm -f kernel
