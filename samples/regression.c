#include <stdio.h>
int main() {
    int a = 10;
    int b = 20;
    int sum = a + b;
    printf("Sum = %d\n", sum);
    if (sum > 25) {
        printf("Greater than 25\n");
    } else {
        printf("25 or less\n");
    }
    printf("Program completed\n");
    return 0;
}
