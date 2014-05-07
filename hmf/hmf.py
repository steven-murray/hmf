'''
This is the primary module for user-interaction with the :mod:`hmf` package.

The module contains a single class, `MassFunction`, which wraps almost all the
functionality of :mod:`hmf` in an easy-to-use way.
'''

version = '1.5.0'

###############################################################################
# Some Imports
###############################################################################
from scipy.interpolate import InterpolatedUnivariateSpline as spline
import scipy.integrate as intg
import numpy as np
from numpy import sin, cos, tan, abs, arctan, arccos, arcsin, exp
import copy
import logging
import cosmolopy as cp
import tools
from fitting_functions import Fits
from transfer import Transfer
from _cache import set_property, cached_property
logger = logging.getLogger('hmf')

#===============================================================================
# Main Class
#===============================================================================
class MassFunction(object):
    """
    An object containing all relevant quantities for the mass function.
    
    The purpose of this class is to calculate many quantities associated with 
    the dark matter halo mass function (HMF). The class is initialized to form a 
    cosmology and takes in various options as to how to calculate all
    further quantities. 
    
    All required outputs are provided as ``@property`` attributes for ease of 
    access.
    
    Contains an update() method which can be passed arguments to update, in the
    most optimal manner. All output quantities are calculated only when needed 
    (but stored after first calculation for quick access).
    
    Quantities related to the transfer function can be accessed through the 
    ``transfer`` property of this object.
    
    Parameters
    ----------   
    M : array_like, optional, default ``np.linspace(10,15,501)``
        The masses at which to perform analysis [units :math:`\log_{10}M_\odot h^{-1}`]. 
                     
    mf_fit : str or callable, optional, default ``"SMT"``
        A string indicating which fitting function to use for :math:`f(\sigma)`
                       
        Available options:
                                           
        1. ``'PS'``: Press-Schechter form from 1974
        #. ``'ST'``: Sheth-Mo-Tormen empirical fit 2001 (deprecated!)
        #. ``'SMT'``: Sheth-Mo-Tormen empirical fit from 2001
        #. ``'Jenkins'``: Jenkins empirical fit from 2001
        #. ``'Warren'``: Warren empirical fit from 2006
        #. ``'Reed03'``: Reed empirical from 2003
        #. ``'Reed07'``: Reed empirical from 2007
        #. ``'Tinker'``: Tinker empirical from 2008
        #. ``'Watson'``: Watson empirical 2012
        #. ``'Watson_FoF'``: Watson Friend-of-friend fit 2012
        #. ``'Crocce'``: Crocce 2010
        #. ``'Courtin'``: Courtin 2011
        #. ``'Angulo'``: Angulo 2012
        #. ``'Angulo_Bound'``: Angulo sub-halo function 2012
        #. ``'Bhattacharya'``: Bhattacharya empirical fit 2011
        #. ``'Behroozi'``: Behroozi extension to Tinker for high-z 2013

        Alternatively, one may define a callable function, with the signature
        ``func(self)``, where ``self`` is a :class:`MassFunction` object (and
        has access to all its attributes). This may be passed here. 
        
    delta_wrt : str, {``"mean"``, ``"crit"``}
        Defines what the overdensity of a halo is with respect to, mean density
        of the universe, or critical density.
                       
    delta_h : float, optional, default ``200.0``
        The overdensity for the halo definition, with respect to ``delta_wrt``
                       
    user_fit : str, optional, default ``""``
        A string defining a mathematical function in terms of `x`, used as
        the fitting function, where `x` is taken as :math:`\( \sigma \)`. Will only
        be applicable if ``mf_fit == "user_model"``.
                                       
    cut_fit : bool, optional, default ``True``
        Whether to forcibly cut :math:`f(\sigma)` at bounds in literature.
        If false, will use whole range of `M`.
           
    delta_c : float, default ``1.686``
        The critical overdensity for collapse, :math:`\delta_c`
        
    kwargs : keywords
        These keyword arguments are sent to the `hmf.transfer.Transfer` class.
        
        Included are all the cosmological parameters (see the docs for details).
        
    """


    def __init__(self, M=None, mf_fit="ST", delta_h=200.0,
                 delta_wrt='mean', cut_fit=True, z2=None, nz=None,
                 delta_c=1.686, mv_scheme="trapz", **kwargs):
        """
        Initializes some parameters      
        """
        if M is None:
            M = np.linspace(10, 15, 501)

        # A list of all available kwargs (sent to Cosmology via Transfer)
        self._cp = ["sigma_8", "n", "w", "cs2_lam", "t_cmb", "y_he", "N_nu",
                    "omegan", "H0", "h", "omegab",
                    "omegac", "omegav", "omegab_h2", "omegac_h2",
                    "force_flat", "default"]

        # Set up a simple dictionary of kwargs which can be later updated
        self._cpdict = {k:v for k, v in kwargs.iteritems() if k in self._cp}

        # Set all given parameters.
        self.mf_fit = mf_fit
        self.M = M
        self.delta_h = delta_h
        self.delta_wrt = delta_wrt
        self.cut_fit = cut_fit
        self.z2 = z2
        self.nz = nz
        self.delta_c = delta_c
        self.transfer = Transfer(**kwargs)
        self.mv_scheme = mv_scheme

        tools.check_kr(self.M[0], self.M[-1], self.cosmo.mean_dens,
                       self.transfer.lnk[0], self.transfer.lnk[-1])
    def update(self, **kwargs):
        """
        Update the class with the given arguments in an optimal manner.
        
        Accepts any argument that the constructor takes.
        """
        for key, val in kwargs.iteritems():

#             The following takes care of everything specifically in this class
            if "_MassFunction__" + key in self.__dict__:
#                 try: doset = np.any(getattr(self, key) != val)
#                 except ValueError: doset = not np.array_equal(getattr(self, key), val)
#                 if doset:
                setattr(self, key, val)

            # We need to handle deletes in this class by parameters in Transfer here
            if key is 'z':
                if val != self.transfer.z:
                    del self.sigma

        # All parameters being sent to Transfer:
        the_rest = {k:v for k, v in kwargs.iteritems() if "_MassFunction__" + k not in self.__dict__}

        # Some things are basically deleted when anything in Transfer is updated
        if len(the_rest) > 0:
            del self.delta_halo
        if len(the_rest) > 1 or (len(the_rest) == 1 and 'z' not in the_rest):
            del self._sigma_0

        # The rest are sent to the Transfer class (stupid values weeded out there)
        self.transfer.update(**the_rest)

        tools.check_kr(self.M[0], self.M[-1], self.cosmo.mean_dens,
                       self.transfer.lnk[0], self.transfer.lnk[-1])

    # --- SET PROPERTIES -------------------------------------------------------
    @set_property("_sigma_0")
    def M(self, val):
        try:
            if len(val) == 1:
                raise ValueError("M must be a sequence of length > 1")
        except TypeError:
            raise TypeError("M must be a sequence of length > 1")

        if np.any(np.abs(np.diff(val, 2)) > 1e-5) or val[1] < val[0]:
            raise ValueError("M must be a linearly increasing vector! " + str(val[0]) + " " + str(val[1]))
        return 10 ** val

    @set_property("fsigma")
    def delta_c(self, val):
        try:
            val = float(val)
        except ValueError:
            raise ValueError("delta_c must be a number: ", val)

        if val <= 0:
            raise ValueError("delta_c must be > 0 (", val, ")")
        if val > 10.0:
            raise ValueError("delta_c must be < 10.0 (", val, ")")

        return val

    @set_property("_sigma_0")
    def mv_scheme(self, val):
        if val not in ['trapz', 'simps', 'romb']:
            raise ValueError("mv_scheme wrong")
        else:
            return val


    @set_property("fsigma")
    def mf_fit(self, val):
        # mf_fit may be a callable or a string. Try callable first.
        try:
            val(self)
        except:
            try:
                val = str(val)
            except:
                raise ValueError("mf_fit must be a string or callable, got ", val)

            if val not in Fits.mf_fits + ["Behroozi"]:
                raise ValueError("mf_fit is not in the list of available fitting functions: ", val)

        return val

    @set_property("delta_halo")
    def delta_h(self, val):
        try:
            val = float(val)
        except ValueError:
            raise ValueError("delta_halo must be a number: ", val)

        if val <= 0:
            raise ValueError("delta_halo must be > 0 (", val, ")")
        if val > 10000:
            raise ValueError("delta_halo must be < 10,000 (", val, ")")

        return val

    @set_property("delta_halo")
    def delta_wrt(self, val):
        if val not in ['mean', 'crit']:
            raise ValueError("delta_wrt must be either 'mean' or 'crit' (", val, ")")

        return val


    @set_property("dndm")
    def z2(self, val):
        if val is None:
            return val

        try:
            val = float(val)
        except ValueError:
            raise ValueError("z must be a number (", val, ")")

        if val <= self.transfer.z:
            raise ValueError("z2 must be larger than z")
        else:
            return val

    @set_property("dndm")
    def nz(self, val):
        if val is None:
            return val

        try:
            val = int(val)
        except ValueError:
            raise ValueError("nz must be an integer")

        if val < 1:
            raise ValueError("nz must be >= 1")
        else:
            return val

    @set_property("fsigma")
    def cut_fit(self, val):
        if not isinstance(val, bool):
            raise ValueError("cut_fit must be a bool, " + str(val))
        return val


    #--------------------------------  START NON-SET PROPERTIES ----------------------------------------------
    @property
    def cosmo(self):
        """ :class:`hmf.cosmo.Cosmology` object aliased from `self.transfer.cosmo`"""
        return self.transfer.cosmo

    @cached_property("fsigma")
    def delta_halo(self):
        """ Overdensity of a halo w.r.t mean density"""
        if self.delta_wrt == 'mean':
            return self.delta_h

        elif self.delta_wrt == 'crit':
            return self.delta_h / cp.density.omega_M_z(self.transfer.z, **self.cosmo.cosmolopy_dict())

    @cached_property("_dlnsdlnm", "sigma")
    def _sigma_0(self):
        """
        The normalised mass variance at z=0 :math:`\sigma`
        
        Notes
        -----
        
        .. math:: \sigma^2(R) = \frac{1}{2\pi^2}\int_0^\infty{k^2P(k)W^2(kR)dk}
        
        """
        return tools.mass_variance(self.M, self.transfer._lnP_0,
                                   self.transfer.lnk,
                                   self.cosmo.mean_dens,
                                   self.mv_scheme)

    @cached_property("dndm", "n_eff")
    def _dlnsdlnm(self):
        """
        The value of :math:`\left|\frac{\d \ln \sigma}{\d \ln M}\right|`, ``len=len(M)``
        
        Notes
        -----
        
        .. math:: frac{d\ln\sigma}{d\ln M} = \frac{3}{2\sigma^2\pi^2R^4}\int_0^\infty \frac{dW^2(kR)}{dM}\frac{P(k)}{k^2}dk
        
        """
        return tools.dlnsdlnm(self.M, self._sigma_0, self.transfer._lnP_0,
                                             self.transfer.lnk,
                                             self.cosmo.mean_dens)

    @cached_property("fsigma", "lnsigma")
    def sigma(self):
        """
        The mass variance at `z`, ``len=len(M)``
        """
        return self._sigma_0 * self.transfer.growth

    @cached_property("fsigma")
    def lnsigma(self):
        """
        Natural log of inverse mass variance, ``len=len(M)``
        """
        return np.log(1 / self.sigma)

    @cached_property()
    def n_eff(self):
        """
        Effective spectral index at scale of halo radius, ``len=len(M)``
        """
        return tools.n_eff(self._dlnsdlnm)

    @cached_property("dndm")
    def fsigma(self):
        """
        The multiplicity function, :math:`f(\sigma)`, for `mf_fit`. ``len=len(M)``
        """
        try:
            fsigma = self.mf_fit(self)
        except:
            fits_class = Fits(self)
            fsigma = fits_class.nufnu()

        if np.sum(np.isnan(fsigma)) > 0.8 * len(fsigma):
            # the input mass range is almost completely outside the cut
            logger.warning("The specified mass-range was almost entirely \
                            outside of the limits from the fit. Ignored fit range...")
            self.cut_fit = False
            try:
                fsigma = self.mf_fit(self)
            except:
                fsigma = fits_class.nufnu()

        return fsigma

    @cached_property("dndlnm", "dndlog10m")
    def dndm(self):
        """
        The number density of haloes, ``len=len(M)`` [units :math:`h^4 M_\odot^{-1} Mpc^{-3}`]
        """
        if self.z2 is None:  # #This is normally the case
            dndm = self.fsigma * self.cosmo.mean_dens * np.abs(self._dlnsdlnm) / self.M ** 2
            if self.mf_fit == 'Behroozi':
                a = 1 / (1 + self.transfer.z)
                theta = 0.144 / (1 + np.exp(14.79 * (a - 0.213))) * (self.M / 10 ** 11.5) ** (0.5 / (1 + np.exp(6.5 * a)))
                ngtm_tinker = self._ngtm()
                ngtm_behroozi = 10 ** (theta + np.log10(ngtm_tinker))
                dthetadM = 0.144 / (1 + np.exp(14.79 * (a - 0.213))) * \
                    (0.5 / (1 + np.exp(6.5 * a))) * (self.M / 10 ** 11.5) ** \
                    (0.5 / (1 + np.exp(6.5 * a)) - 1) / (10 ** 11.5)
                dndm = self.__dndm * 10 ** theta - ngtm_behroozi * np.log(10) * dthetadM
        else:  # #This is for a survey-volume weighted calculation
            if self.nz is None:
                self.nz = 10
            zedges = np.linspace(self.transfer.z, self.z2, self.nz)
            zcentres = (zedges[:-1] + zedges[1:]) / 2
            dndm = np.zeros_like(zcentres)
            vol = np.zeros_like(zedges)
            vol[0] = cp.distance.comoving_volume(self.transfer.z,
                                        **self.cosmo.cosmolopy_dict())
            for i, zz in enumerate(zcentres):
                self.update(z=zz)
                dndm[i] = self.fsigma * self.cosmo.mean_dens * np.abs(self._dlnsdlnm) / self.M ** 2
                if self.mf_fit == 'Behroozi':
                    a = 1 / (1 + self.transfer.z)
                    theta = 0.144 / (1 + np.exp(14.79 * (a - 0.213))) * (self.M / 10 ** 11.5) ** (0.5 / (1 + np.exp(6.5 * a)))
                    ngtm_tinker = self._ngtm()
                    ngtm_behroozi = 10 ** (theta + np.log10(ngtm_tinker))
                    dthetadM = 0.144 / (1 + np.exp(14.79 * (a - 0.213))) * (0.5 / (1 + np.exp(6.5 * a))) * (self.M / 10 ** 11.5) ** (0.5 / (1 + np.exp(6.5 * a)) - 1) / (10 ** 11.5)
                    dndm[i] = dndm[i] * 10 ** theta - ngtm_behroozi * np.log(10) * dthetadM

                vol[i + 1] = cp.distance.comoving_volume(z=zedges[i + 1],
                                                **self.cosmo.cosmolopy_dict())

            vol = vol[1:] - vol[:-1]  # Volume in shells
            integrand = vol * dndm
            numerator = intg.simps(integrand, x=zcentres)
            denom = intg.simps(vol, zcentres)
            dndm = numerator / denom
        return dndm

    @cached_property("ngtm", "nltm", "mgtm", "mltm", "how_big")
    def dndlnm(self):
        """
        The differential mass function in terms of natural log of `M`, ``len=len(M)`` [units :math:`h^3 Mpc^{-3}`]
        """
        return self.M * self.dndm

    @cached_property()
    def dndlog10m(self):
        """
        The differential mass function in terms of log of `M`, ``len=len(M)`` [units :math:`h^3 Mpc^{-3}`]
        """
        return self.M * self.dndm * np.log(10)

    def _upper_ngtm(self, M, mass_function, cut):
        """Calculate the mass function above given range of `M` in order to integrate"""
        # mass_function is logged already (not log10 though)
        m_upper = np.linspace(np.log(M[-1]), np.log(10 ** 18), 500)
        if cut:  # since its been cut, the best we can do is a power law
            mf_func = spline(np.log(M), mass_function, k=1)
            mf = mf_func(m_upper)
        else:
            # We try to calculate the hmf as far as we can normally
            new_pert = copy.deepcopy(self)
            new_pert.update(M=np.log10(np.exp(m_upper)))
            mf = np.log(np.exp(m_upper) * new_pert.dndm)

            if np.isnan(mf[-1]):  # Then we couldn't get up all the way, so have to do linear ext.
                if np.isnan(mf[1]):  # Then the whole extension is nan and we have to use the original (start at 1 because 1 val won't work either)
                    mf_func = spline(np.log(M), mass_function, k=1)
                    mf = mf_func(m_upper)
                else:
                    mfslice = mf[np.logical_not(np.isnan(mf))]
                    m_nan = m_upper[np.isnan(mf)]
                    m_true = m_upper[np.logical_not(np.isnan(mf))]
                    mf_func = spline(m_true, mfslice, k=1)
                    mf[len(mfslice):] = mf_func(m_nan)
        return m_upper, mf

    def _lower_ngtm(self, M, mass_function, cut):
        ### WE CALCULATE THE MASS FUNCTION BELOW THE COMPUTED RANGE ###
        # mass_function is logged already (not log10 though)
        m_lower = np.linspace(np.log(10 ** 3), np.log(M[0]), 500)
        if cut:  # since its been cut, the best we can do is a power law
            mf_func = spline(np.log(M), mass_function, k=1)
            mf = mf_func(m_lower)
        else:
            # We try to calculate the hmf as far as we can normally
            new_pert = copy.deepcopy(self)
            new_pert.update(M=np.log10(np.exp(m_lower)))
            mf = np.log(np.exp(m_lower) * new_pert.dndm)

            if np.isnan(mf[0]):  # Then we couldn't go down all the way, so have to do linear ext.
                mfslice = mf[np.logical_not(np.isnan(mf))]
                m_nan = m_lower[np.isnan(mf)]
                m_true = m_lower[np.logical_not(np.isnan(mf))]
                mf_func = spline(m_true, mfslice, k=1)
                mf[:len(m_nan)] = mf_func(m_nan)
        return m_lower, mf

    def _ngtm(self):
        """
        Calculate n(>m).
        
        This function is separated from the property because of the Behroozi fit
        """
        # set M and mass_function within computed range
        M = self.M[np.logical_not(np.isnan(self.dndlnm))]
        mass_function = self.dndlnm[np.logical_not(np.isnan(self.dndlnm))]

        # Calculate the mass function (and its integral) from the highest M up to 10**18
        if M[-1] < 10 ** 18:
            m_upper, mf = self._upper_ngtm(M, np.log(mass_function), M[-1] < self.M[-1])

            int_upper = intg.simps(np.exp(mf), dx=m_upper[2] - m_upper[1], even='first')
        else:
            int_upper = 0

        # Calculate the cumulative integral (backwards) of mass_function (Adding on the upper integral)
        ngtm = np.concatenate((intg.cumtrapz(mass_function[::-1], dx=np.log(M[1]) - np.log(M[0]))[::-1], np.zeros(1))) + int_upper

        # We need to set ngtm back in the original length vector with nans where they were originally
        if len(ngtm) < len(self.M):
            ngtm_temp = np.zeros_like(self.dndlnm)
            ngtm_temp[:] = np.nan
            ngtm_temp[np.logical_not(np.isnan(self.dndlnm))] = ngtm
            ngtm = ngtm_temp

        return ngtm

    @cached_property("how_big")
    def ngtm(self):
        """
        The cumulative mass function above `M`, ``len=len(M)`` [units :math:`h^3 Mpc^{-3}`]
        """
        return self._ngtm()

    @cached_property()
    def mgtm(self):
        """
        Mass in haloes `>M`, ``len=len(M)`` [units :math:`M_\odot h^2 Mpc^{-3}`]
        """
        M = self.M[np.logical_not(np.isnan(self.dndlnm))]
        mass_function = self.dndlnm[np.logical_not(np.isnan(self.dndlnm))]

        # Calculate the mass function (and its integral) from the highest M up to 10**18
        if M[-1] < 10 ** 18:
            m_upper, mf = self._upper_ngtm(M, np.log(mass_function), M[-1] < self.M[-1])
            int_upper = intg.simps(np.exp(mf + m_upper) , dx=m_upper[2] - m_upper[1], even='first')
        else:
            int_upper = 0

        # Calculate the cumulative integral (backwards) of mass_function (Adding on the upper integral)
        mgtm = np.concatenate((intg.cumtrapz(mass_function[::-1] * M[::-1], dx=np.log(M[1]) - np.log(M[0]))[::-1], np.zeros(1))) + int_upper

        # We need to set ngtm back in the original length vector with nans where they were originally
        if len(mgtm) < len(self.M):
            mgtm_temp = np.zeros_like(self.dndlnm)
            mgtm_temp[:] = np.nan
            mgtm_temp[np.logical_not(np.isnan(self.dndlnm))] = mgtm
            mgtm = mgtm_temp
        return mgtm

    @cached_property()
    def nltm(self):
        """
        Inverse cumulative mass function, ``len=len(M)`` [units :math:`h^3 Mpc^{-3}`]
        """
        # set M and mass_function within computed range
        M = self.M[np.logical_not(np.isnan(self.dndlnm))]
        mass_function = self.dndlnm[np.logical_not(np.isnan(self.dndlnm))]

        # Calculate the mass function (and its integral) from 10**3 up to lowest M
        if M[0] > 10 ** 3:
            m_lower, mf = self._lower_ngtm(M, np.log(mass_function), M[0] > self.M[0])

            int_lower = intg.simps(np.exp(mf), dx=m_lower[2] - m_lower[1], even='first')
        else:
            int_lower = 0

        # Calculate the cumulative integral of mass_function (Adding on the lower integral)
        nltm = np.concatenate((np.zeros(1), intg.cumtrapz(mass_function, dx=np.log(M[1]) - np.log(M[0])))) + int_lower

        # We need to set ngtm back in the original length vector with nans where they were originally
        if len(nltm) < len(self.M):
            nltm_temp = np.zeros_like(self.dndlnm)
            nltm_temp[:] = np.nan
            nltm_temp[np.logical_not(np.isnan(self.dndlnm))] = nltm
            nltm = nltm_temp

        return nltm

    @cached_property()
    def mltm(self):
        """
        Total mass in haloes `<M`, ``len=len(M)`` [units :math:`M_\odot h^2 Mpc^{-3}`]
        """
        # Set M within calculated range
        M = self.M[np.logical_not(np.isnan(self.dndlnm))]
        mass_function = self.dndlnm[np.logical_not(np.isnan(self.dndlnm))]

        # Calculate the mass function (and its integral) from 10**3 up to lowest M
        if M[0] > 10 ** 3:
            m_lower, mf = self._lower_ngtm(M, np.log(mass_function), M[0] > self.M[0])

            int_lower = intg.simps(np.exp(mf + m_lower), dx=m_lower[2] - m_lower[1], even='first')
        else:
            int_lower = 0

        # Calculate the cumulative integral of mass_function (Adding on the lower integral)
        mltm = np.concatenate((np.zeros(1), intg.cumtrapz(mass_function * M, dx=np.log(M[1]) - np.log(M[0])))) + int_lower

        # We need to set ngtm back in the original length vector with nans where they were originally
        if len(mltm) < len(self.M):
            nltm_temp = np.zeros_like(self.dndlnm)
            nltm_temp[:] = np.nan
            nltm_temp[np.logical_not(np.isnan(self.dndlnm))] = mltm
            mltm = nltm_temp

        return mltm

    @cached_property()
    def how_big(self):
        """ 
        Size of simulation volume in which to expect one halo of mass M, ``len=len(M)`` [units :math:`Mpch^{-1}`]
        """

        return self.ngtm ** (-1. / 3.)
