#include <stdio.h>

int square(int n) {
    return n * n;
}

int main() {
    int numbers[5] = {2, 4, 6, 8, 10};
    int sum = 0;
    int i = 0;

    for (i = 0; i < 5; i++) {
        sum += square(numbers[i]);
    }

    printf("sum=%d\n", sum);
    return 0;
}
