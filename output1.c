#include <stdio.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    int id;
    char name[50];
} Student;

void display(Student *s) {
    printf("%d %s\n", s->id, s->name);
}

void updateStudent(Student * s, int newId) {
    s->id = newId;
}

int main(void) {
    Student student1 = (Student){101, "Anish"};
    updateStudent(&student1, 105);
    display(&student1);
    return 0;
}
