#include "../../Unvanquished/libs/glm/glm/vec3.hpp"

float GLMIndexingUB()
{
    // TODO: length other than 3
    glm::vec3 v{};
    float a = v[0];
    float b = v.y;

    float* c = &v[0]; //!

    // TODO: alert on &v.x

    void f(float&);
    f(v.z);

    glm::vec3* pv = &v;
    return a + b + *c + pv->x;
}
