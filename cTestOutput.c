#include <stdio.h>
#include <stdbool.h>
#include <string.h>

typedef struct {
    char brand[50];
    char model[50];
    int speed;
} Vehicle;

void Vehicle_display_details(Vehicle *s) {
    printf("%s %s\n", "Brand:", s->brand);
    printf("%s %s\n", "Model:", s->model);
    printf("%s %d\n", "Speed:", s->speed);
}

void Vehicle_start(Vehicle *s) {
    printf("%s %s\n", s->brand, "vehicle is starting.");
}

typedef struct {
    char brand[50];
    char model[50];
    int speed;
    char fuel_type[50];
} Car;

void Car_start(Car *s) {
    printf("%s %s %s\n", s->brand, "car is starting with", s->fuel_type);
}

void Car_display_details(Car *s) {
    Vehicle_display_details((Vehicle *)s);
    printf("%s %s\n", "Fuel Type:", s->fuel_type);
}

typedef struct {
    char brand[50];
    char model[50];
    int speed;
    int engine_cc;
} Bike;

void Bike_start(Bike *s) {
    printf("%s %s\n", s->brand, "bike is starting.");
}

void Bike_display_details(Bike *s) {
    Vehicle_display_details((Vehicle *)s);
    printf("%s %d\n", "Engine CC:", s->engine_cc);
}


int main(void) {
    Car car1 = (Car){"Toyota", "Fortuner", 180, "Diesel"};
    Bike bike1 = (Bike){"Yamaha", "R15", 140, 155};
    printf("%s\n", "----- CAR DETAILS -----");
    Car_display_details(&car1);
    Car_start(&car1);
    printf("%s\n", "\n----- BIKE DETAILS -----");
    Bike_display_details(&bike1);
    Bike_start(&bike1);
    printf("%s\n", "\n----- POLYMORPHISM -----");
    /* vehicles = [car1, bike1] */
    Car_start(&car1);
    Bike_start(&bike1);
    return 0;
}
