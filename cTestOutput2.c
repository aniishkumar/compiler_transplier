#include <stdio.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    char name[50];
    int age;
    char city[50];
} Person;

void Person_display_details(Person *s) {
    printf("%s %s\n", "Name:", s->name);
    printf("%s %d\n", "Age:", s->age);
    printf("%s %s\n", "City:", s->city);
}

void Person_introduce(Person *s) {
    printf("%s %s\n", s->name, "is a person.");
}

typedef struct {
    char name[50];
    int age;
    char city[50];
    int roll_number;
    char course[50];
} Student;

void Student_introduce(Student *s) {
    printf("%s %s %s\n", s->name, "is a student studying", s->course);
}

void Student_display_details(Student *s) {
    Person_display_details((Person *)s);
    printf("%s %d\n", "Roll Number:", s->roll_number);
    printf("%s %s\n", "Course:", s->course);
}

typedef struct {
    char name[50];
    int age;
    char city[50];
    char subject[50];
    int experience;
} Teacher;

void Teacher_introduce(Teacher *s) {
    printf("%s %s %s\n", s->name, "is teaching", s->subject);
}

void Teacher_display_details(Teacher *s) {
    Person_display_details((Person *)s);
    printf("%s %s\n", "Subject:", s->subject);
    printf("%s %d %s\n", "Experience:", s->experience, "years");
}


int main(void) {
    Student student = (Student){"Anish", 20, "Vellore", 101, "Computer Science"};
    Teacher teacher = (Teacher){"Rahul", 35, "Chennai", "Python", 10};
    printf("%s\n", "----- Student Details -----");
    Student_display_details(&student);
    Student_introduce(&student);
    printf("%s\n", "\n----- Teacher Details -----");
    Teacher_display_details(&teacher);
    Teacher_introduce(&teacher);
    return 0;
}
