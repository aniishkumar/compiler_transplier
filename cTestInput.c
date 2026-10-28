#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Structure declaration
struct Employee {
    int id;
    char name[50];
    float salary;
};

// Function to display employee details
void display(struct Employee *ptr, int n) {

    for (int i = 0; i < n; i++) {

        printf("\nEmployee %d\n", i + 1);
        printf("ID: %d\n", (ptr + i)->id);
        printf("Name: %s\n", (ptr + i)->name);
        printf("Salary: %.2f\n", (ptr + i)->salary);
    }
}

int main() {

    int n;

    printf("Enter number of employees: ");
    scanf("%d", &n);

    // Pointer declaration
    struct Employee *ptr;

    // Dynamic memory allocation
    ptr = (struct Employee *)malloc(n * sizeof(struct Employee));

    // Check memory allocation
    if (ptr == NULL) {
        printf("Memory allocation failed!\n");
        return 1;
    }

    // Input employee details
    for (int i = 0; i < n; i++) {

        printf("\nEnter Employee %d details\n", i + 1);

        printf("Enter ID: ");
        scanf("%d", &((ptr + i)->id));

        printf("Enter Name: ");
        scanf("%49s", (ptr + i)->name);

        printf("Enter Salary: ");
        scanf("%f", &((ptr + i)->salary));
    }

    // Display employee details
    printf("\n----- Employee Records -----\n");

    display(ptr, n);

    // Free allocated memory
    free(ptr);
    ptr = NULL;

    printf("\nMemory successfully freed!\n");

    return 0;
}