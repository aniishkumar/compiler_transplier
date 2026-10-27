#include <stdio.h>
#include <stdlib.h>

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

    // Dynamic memory allocation
    struct Student *ptr;

    ptr = (struct Student *)malloc(n * sizeof(struct Student));

    // Check memory allocation
    if (ptr == NULL) {
        printf("Memory allocation failed!\n");
        return 1;
    }

    // Taking student details
    for (int i = 0; i < n; i++) {

        printf("\nEnter details of student %d\n", i + 1);

        printf("Enter ID: ");
        scanf("%d", &(ptr + i)->id);

        printf("Enter Name: ");
        scanf("%49s", (ptr + i)->name);

        printf("Enter Marks: ");
        scanf("%f", &(ptr + i)->marks);
    }

    // Display student details
    printf("\n----- Student Details -----\n");

    for (int i = 0; i < n; i++) {

        printf("\nStudent %d\n", i + 1);

        printf("ID: %d\n", (ptr + i)->id);
        printf("Name: %s\n", (ptr + i)->name);
        printf("Marks: %.2f\n", (ptr + i)->marks);
    }

    // Reallocating memory
    int new_n;

    printf("\nEnter new number of students: ");
    scanf("%d", &new_n);

    if (new_n > 0) {

        struct Student *temp = realloc(ptr, new_n * sizeof(struct Student));

        if (temp == NULL) {
            printf("Reallocation failed!\n");
            free(ptr);
            return 1;
        }

        ptr = temp;

        // Input additional students
        for (int i = n; i < new_n; i++) {

            printf("\nEnter details of student %d\n", i + 1);

            printf("Enter ID: ");
            scanf("%d", &ptr[i].id);

            printf("Enter Name: ");
            scanf("%49s", ptr[i].name);

            printf("Enter Marks: ");
            scanf("%f", &ptr[i].marks);
        }

        n = new_n;
    }

    // Free dynamically allocated memory
    free(ptr);
    ptr = NULL;

    printf("\nMemory successfully freed!\n");

    return 0;
}