#include <stdio.h>
#include <stdlib.h>
#include <string.h>

// Structure declaration
struct Student {
    int id;
    char name[50];
    float marks;
};

int main() {

    int n;

    printf("Enter number of students: ");
    scanf("%d", &n);

    // Pointer declaration
    struct Student *ptr;

    // Dynamic memory allocation
    ptr = (struct Student *)malloc(n * sizeof(struct Student));

    // Check allocation
    if (ptr == NULL) {
        printf("Memory allocation failed!");
        return 1;
    }

    // Input student details
    for (int i = 0; i < n; i++) {

        printf("\nEnter details for student %d\n", i + 1);

        printf("Enter ID: ");
        scanf("%d", &(ptr + i)->id);

        printf("Enter Name: ");
        scanf("%49s", (ptr + i)->name);

        printf("Enter Marks: ");
        scanf("%f", &(ptr + i)->marks);
    }

    // Display student details
    printf("\n----- Student Records -----\n");

    for (int i = 0; i < n; i++) {

        printf("\nID: %d", ptr[i].id);
        printf("\nName: %s", ptr[i].name);
        printf("\nMarks: %.2f\n", ptr[i].marks);
    }

    // Free dynamically allocated memory
    free(ptr);
    ptr = NULL;

    printf("\nMemory freed successfully!\n");

    return 0;
}