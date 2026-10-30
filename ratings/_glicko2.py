"""
Rust-backed adapter derived from Heungsub Lee's `glicko2` package (2012, BSD license).
Original: https://github.com/sublee/glicko2
Full licence notice: rust/rating_rs/LICENSE.

Numerical updates and inactivity transitions are implemented in rust/rating_rs.
"""
import rating_rs

WIN = 1.
DRAW = 0.5
LOSS = 0.

MU = 1500
PHI = 350
SIGMA = 0.06
TAU = 1.0
EPSILON = 0.000001


class Rating:
    def __init__(self, mu=MU, phi=PHI, sigma=SIGMA):
        self.mu = mu
        self.phi = phi
        self.sigma = sigma

    def __repr__(self):
        c = type(self)
        args = (c.__module__, c.__name__, self.mu, self.phi, self.sigma)
        return '{}.{}(mu={:.3f}, phi={:.3f}, sigma={:.3f})'.format(*args)


class Glicko2:
    def __init__(self, mu=MU, phi=PHI, sigma=SIGMA, tau=TAU, epsilon=EPSILON):
        self.mu = mu
        self.phi = phi
        self.sigma = sigma
        self.tau = tau
        self.epsilon = epsilon

    def create_rating(self, mu=None, phi=None, sigma=None):
        if mu is None:
            mu = self.mu
        if phi is None:
            phi = self.phi
        if sigma is None:
            sigma = self.sigma
        return Rating(mu, phi, sigma)

    def scale_down(self, rating, ratio=173.7178):
        mu = (rating.mu - self.mu) / ratio
        phi = rating.phi / ratio
        return self.create_rating(mu, phi, rating.sigma)

    def rate(self, rating, series):
        return self.rate_weighted(rating, ((score, opponent, 1.0) for score, opponent in series))

    def inflate(self, rating, periods):
        if periods <= 0:
            return rating
        mu, phi, sigma = rating_rs.inflate(rating.mu, rating.phi, rating.sigma, self.mu, periods)
        return self.create_rating(mu, phi, sigma)

    def rate_weighted(self, rating, series):
        """Rate against ``(score, opponent, weight)`` results.

        Unit weights follow the same Glicko-2 operations as ``rate``. A zero
        total information update is treated as an inactive period.
        """
        values = [(score, other.mu, other.phi, weight) for score, other, weight in series]
        mu, phi, sigma = rating_rs.rate(
            rating.mu, rating.phi, rating.sigma, values, self.mu, self.tau, self.epsilon,
        )
        return self.create_rating(mu, phi, sigma)
