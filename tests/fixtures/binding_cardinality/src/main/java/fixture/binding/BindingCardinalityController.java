package fixture.binding;

import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.http.HttpSession;
import org.springframework.ui.Model;
import org.springframework.ui.ModelMap;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BindingCardinalityController {
    private static final Map<String, UserDto> implicitUsers = new LinkedHashMap<>();
    private static final Map<String, UserDto> explicitUsers = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> dense = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> densePlusTwo = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> other = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> sparse = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> unknownInit = new LinkedHashMap<>();
    private static final Map<Integer, UserDto> mutated = new LinkedHashMap<>();

    static {
        dense.put(1, new UserDto("seed-1"));
        dense.put(2, new UserDto("seed-2"));
        densePlusTwo.put(1, new UserDto("seed-1"));
        densePlusTwo.put(2, new UserDto("seed-2"));
        other.put(1, new UserDto("seed-1"));
        other.put(2, new UserDto("seed-2"));
        sparse.put(2, new UserDto("seed-2"));
        seedUnknown(unknownInit);
        mutated.put(1, new UserDto("seed-1"));
        mutated.put(2, new UserDto("seed-2"));
    }

    private static void seedUnknown(Map<Integer, UserDto> target) {
        target.put(1, new UserDto("seed"));
    }

    @PostMapping("/implicit")
    public void implicit(UserDto user) {
        implicitUsers.put(user.getId(), user); // implicit-getter-growth
    }

    @PostMapping("/explicit")
    public void explicit(@ModelAttribute UserDto user) {
        explicitUsers.put(user.getId(), user); // explicit-getter-growth
    }

    @PostMapping("/fresh")
    public void fresh(UserDto user) {
        int id = dense.size() + 1;
        dense.put(id, user); // dense-fresh-growth
    }

    @PostMapping("/fresh-plus-two")
    public void freshPlusTwo(UserDto user) {
        densePlusTwo.put(densePlusTwo.size() + 2, user); // dense-plus-two-growth
    }

    @PostMapping("/different-map")
    public void differentMap(UserDto user) {
        dense.put(other.size() + 1, user); // different-map-growth
    }

    @PostMapping("/zero")
    public void zero(UserDto user) {
        dense.put(dense.size() + 0, user); // zero-offset-growth
    }

    @PostMapping("/subtract")
    public void subtract(UserDto user) {
        dense.put(dense.size() - 1, user); // subtraction-growth
    }

    @PostMapping("/unknown-offset")
    public void unknownOffset(UserDto user, @RequestParam int offset) {
        dense.put(dense.size() + offset, user); // unknown-offset-growth
    }

    @PostMapping("/request-local")
    public void requestLocal(UserDto user) {
        Map<Integer, UserDto> local = new LinkedHashMap<>();
        local.put(local.size() + 1, user); // request-local-growth
    }

    @PostMapping("/sparse")
    public void sparse(UserDto user) {
        sparse.put(sparse.size() + 1, user); // sparse-growth
    }

    @PostMapping("/unknown-init")
    public void unknownInit(UserDto user) {
        unknownInit.put(unknownInit.size() + 1, user); // unknown-init-growth
    }

    @PostMapping("/mutated")
    public void mutated(UserDto user) {
        mutated.remove(1);
        mutated.put(mutated.size() + 1, user); // selected-handler-mutation-growth
    }

    @PostMapping("/fixed")
    public void fixed(UserDto user) {
        dense.put(7, user); // fixed-key-growth
    }

    @PostMapping("/framework-values")
    public void frameworkValues(
        Model model,
        ModelMap modelMap,
        BindingResult bindingResult,
        HttpServletRequest request,
        HttpServletResponse response,
        HttpSession session,
        Principal principal,
        String text,
        Integer boxed
    ) {}

    public static final class UserDto {
        private final String id;

        public UserDto(String id) {
            this.id = id;
        }

        public String getId() {
            return id;
        }
    }
}
