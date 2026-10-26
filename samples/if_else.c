#include <stdio.h>
int main() {
    int count = 2;
    if (count > 1 && count < 4) {
        printf("%d\n", count + 3);
    } else {
        printf("%d\n", 0);
    }
    return 0;
}
