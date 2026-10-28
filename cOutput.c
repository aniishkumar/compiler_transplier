#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int id;
    char name[50];
    float marks;
} Student;

int main(void) {
    int n = 0;
    printf("Enter number of students: ");
    scanf("%d", &n);
    Student *ptr;
    ptr = (struct Student*)(malloc((n * sizeof(struct Student))));
    if ((ptr == NULL)) {
        printf("Memory allocation failed!\n");
        return 1;
    }
    for (int i = 0; (i < n); i++) {
        printf("\nEnter details of student %d\n", (i + 1));
        printf("Enter ID: ");
        scanf("%d", &(ptr + i)->id);
        printf("Enter Name: ");
        scanf("%49s", (ptr + i)->name);
        printf("Enter Marks: ");
        scanf("%f", &(ptr + i)->marks);
    }
    printf("\n----- Student Details -----\n");
    for (int i = 0; (i < n); i++) {
        printf("\nStudent %d\n", (i + 1));
        printf("ID: %d\n", (ptr + i)->id);
        printf("Name: %s\n", (ptr + i)->name);
        printf("Marks: %.2f\n", (ptr + i)->marks);
    }
    int new_n = 0;
    printf("\nEnter new number of students: ");
    scanf("%d", &new_n);
    if ((new_n > 0)) {
        Student *temp = realloc(ptr, (new_n * sizeof(struct Student)));
        if ((temp == NULL)) {
            printf("Reallocation failed!\n");
            free(ptr);
            return 1;
        }
        ptr = temp;
        for (int i = n; (i < new_n); i++) {
            printf("\nEnter details of student %d\n", (i + 1));
            printf("Enter ID: ");
            scanf("%d", &ptr[i].id);
            printf("Enter Name: ");
            scanf("%49s", ptr[i].name);
            printf("Enter Marks: ");
            scanf("%f", &ptr[i].marks);
        }
        n = new_n;
    }
    free(ptr);
    ptr = NULL;
    printf("\nMemory successfully freed!\n");
    return 0;
}
